"""Narrow Jyshare mortgage strategy; independent arithmetic precedes DOM binding.

This module calculates fixed-payment mortgage figures from explicit numeric
inputs. Actual page behavior and collected frames require separate verification.
"""
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP, localcontext
from urllib.parse import urlsplit

ADAPTER_ID='jyshare-mortgage-widget-1'
STRATEGY_ID='mortgage-equal-payment-v1'
URI='https://www.jyshare.com/front-end/9986/'


def matches_uri(uri):
    return urlsplit(uri)==urlsplit(URI)


def equal_payment_oracle(principal_wan,annual_rate_percent,years):
    """Unrounded annuity payment, then independently rounded displayed totals.

    Scope is positive fixed-rate, integer-year monthly equal payments. Display
    totals are calculated from the unrounded payment, rather than multiplying
    the rounded displayed installment; the actual website must be checked for
    its convention before this oracle is bound to a task.
    """
    try:
        principal=Decimal(str(principal_wan))*10000
        annual=Decimal(str(annual_rate_percent))
        term=Decimal(str(years))
    except (InvalidOperation,ValueError) as error:
        raise ValueError('Loan inputs must be numeric') from error
    if not all(value.is_finite() for value in (principal,annual,term)) or not (
            0<principal<=Decimal('1000000000') and 0<annual<=100 and term==term.to_integral_value() and 1<=term<=100):
        raise ValueError('Unsupported principal, fixed rate or integer-year term')
    with localcontext() as context:
        context.prec=60
        months=int(term)*12
        monthly_rate=annual/1200
        factor=(1+monthly_rate)**months
        monthly=principal*monthly_rate*factor/(factor-1)
        total=monthly*months
        interest=total-principal
        fmt=lambda value:format(value.quantize(Decimal('0.01'),rounding=ROUND_HALF_UP),'.2f')
        return {'principal_yuan':fmt(principal),'monthly_rate':str(monthly_rate),'months':months,
                'monthly_payment':fmt(monthly),'total_payment':fmt(total),'total_interest':fmt(interest),
                'monthly_payment_unrounded':str(monthly),'rounding':'ROUND_HALF_UP two decimal places after unrounded annuity calculation'}


LOAN_INVENTORY_JS=r'''() => {
 const empty={widgets:[],result_targets:[],widget_rejections:[]};
 if(location.href!=='https://www.jyshare.com/front-end/9986/')return empty;
 const id='jyshare-mortgage-widget-1',clean=s=>(s||'').replace(/\s+/g,' ').trim();
 const fail=reason=>({...empty,widget_rejections:[{adapter_id:id,page_uri:location.href,reason}]});
 const one=(selector,root=document)=>root.querySelectorAll(selector).length===1?root.querySelector(selector):null;
 const visible=e=>{if(!e||!e.checkVisibility({checkOpacity:true,checkVisibilityCSS:true}))return false;
  const r=e.getBoundingClientRect(),hit=document.elementFromPoint((r.left+r.right)/2,(r.top+r.bottom)/2);
  return r.width>0&&r.height>0&&r.left>=0&&r.top>=0&&r.right<=innerWidth&&r.bottom<=innerHeight&&!!hit&&(hit===e||e.contains(hit));};
 const amount=one('#loanAmount'),term=one('#loanTerm'),rate=one('#interestRate'),repayment=one('#repaymentType');
 const button=one('button[onclick="calculateMortgage()"]'),mode=one('#loanModeGroup'),result=one('#resultContainer');
 if(!amount||!term||!rate||!repayment||!button||!mode||!result)return fail('Mortgage requires unique observed controls/results');
 const root=amount.closest('.calculator-container');
 if(!root||![term,rate,repayment,button,mode,result].every(e=>root.contains(e))||amount.form||term.form)
  return fail('Mortgage non-form grouping changed');
 const editable=[...root.querySelectorAll('input,textarea,select,button,[contenteditable=true]')]
  .filter(e=>e.checkVisibility({checkOpacity:true,checkVisibilityCSS:true}));
 const modeButtons=[...mode.querySelectorAll('button')];
 if(modeButtons.length!==3||editable.length!==8||editable.some(e=>![amount,term,rate,repayment,button,...modeButtons].includes(e)))
  return fail('Mortgage visible controls changed');
 const modes=[['normal','商业贷款'],['provident','公积金贷款'],['combine','组合贷款']];
 for(let n=0;n<modes.length;n++){
  const e=modeButtons[n];if(e.dataset.mode!==modes[n][0]||clean(e.innerText)!==modes[n][1]||e.disabled||!visible(e)||
     e.classList.contains('active')!==(n===0))return fail('Mortgage commercial mode or original mode buttons changed');
 }
 const fields=[];let rateSetting;
 for(const [e,label,expectedInitial] of [[amount,'贷款金额（万元）','100'],[term,'贷款期限（年）','20'],[rate,'年利率（%）','3.05']]){
  const labels=[...(e.labels||[])];
  if(e.localName!=='input'||e.type!=='number'||e.disabled||e.readOnly||!visible(e)||labels.length!==1||
    !visible(labels[0])||clean(labels[0].innerText)!==label||e.value!==expectedInitial)
   return fail('Mortgage numeric role, native associated label or initial value changed');
  const field={selector:'#'+e.id,tag:'input',type:'number',label,visible:true,enabled:true,value:e.value,
   label_source:'native_associated_label',min:e.min||'',max:e.max||'',step:e.step||'',placeholder:e.placeholder||'',options:[]};
  if(e===rate)rateSetting=field;else fields.push(field);
 }
 const repayLabels=[...(repayment.labels||[])];
 if(repayment.localName!=='select'||repayment.disabled||!visible(repayment)||repayLabels.length!==1||!visible(repayLabels[0])||
   clean(repayLabels[0].innerText)!=='还款方式'||repayment.value!=='equalPayment'||
   repayment.options.length!==2||repayment.options[0].value!=='equalPayment'||clean(repayment.options[0].textContent)!=='等额本息'||
   repayment.options[1].value!=='equalPrincipal'||clean(repayment.options[1].textContent)!=='等额本金')
  return fail('Mortgage fixed equal-payment setting changed');
 if(button.localName!=='button'||button.type!=='button'||button.disabled||!visible(button)||clean(button.innerText)!=='立即计算')
  return fail('Mortgage calculate button changed');
 fields.push({selector:'button[onclick="calculateMortgage()"]',tag:'button',type:'button',label:'立即计算',visible:true,enabled:true,value:''});
 const resultHeading=one('.card-title',result);
 if(!resultHeading||clean(resultHeading.textContent)!=='还款概览')return fail('Mortgage summary heading changed');
 const targets=[];
 for(const [rid,label] of [['monthlyPayment','月供'],['totalPayment','总还款'],['totalInterest','总利息']]){
  const e=one('#'+rid),caption=e?.previousElementSibling;
  if(!e||!result.contains(e)||e.localName!=='h4'||!caption||caption.localName!=='p'||clean(caption.textContent)!==label)
   return fail('Mortgage result role changed');
  targets.push({selector:'#'+rid,text:clean(e.textContent),visible:visible(e),label,business_label:'房贷等额本息',unit:'元'});
 }
 return {widgets:[{kind:'non-form-widget',adapter_id:id,page_uri:location.href,label:'房贷计算器',fields,
  fixed_rate:rateSetting,loan_mode:{selector:'#loanModeGroup button[data-mode="normal"]',value:'normal',label:'商业贷款',visible:true,selected:true},
  repayment:{selector:'#repaymentType',value:'equalPayment',label:'还款方式',display:'等额本息',visible:true,enabled:true},
  result_heading:'还款概览',result_selector:'#resultContainer',result_initially_visible:result.checkVisibility({checkOpacity:true,checkVisibilityCSS:true}),
  viewport:[innerWidth,innerHeight],observed_scroll_y:scrollY}],result_targets:targets,widget_rejections:[]};
}'''


def validate_observation(capability,page,widget):
    if not all(matches_uri(u) for u in (capability['site_uri'],page['page_uri'],widget.get('page_uri',''))):
        raise ValueError('Mortgage requires its exact observed URI')
    if (widget.get('kind'),widget.get('adapter_id'),widget.get('label'))!=('non-form-widget',ADAPTER_ID,'房贷计算器'):
        raise ValueError('Mortgage typed widget identity changed')
    if widget.get('viewport')!=[1280,720] or widget.get('observed_scroll_y')!=0:
        raise ValueError('Mortgage inputs require observed initial production viewport')
    fields=widget['fields'];submit='button[onclick="calculateMortgage()"]'
    if len(fields)!=3 or {f['selector'] for f in fields}!={'#loanAmount','#loanTerm',submit}:
        raise ValueError('Mortgage requires exactly two changing inputs and submit')
    by_id={f['selector']:f for f in fields};inputs=[]
    for selector,label,initial,value,minval,step in [('#loanAmount','贷款金额（万元）','100','12','','0.1'),
                                                    ('#loanTerm','贷款期限（年）','20','1','1','')]:
        f=by_id[selector]
        if (f.get('tag'),f.get('type'),f.get('label'),f.get('visible'),f.get('enabled'),f.get('value'),f.get('label_source'),f.get('min'),f.get('max'),f.get('step'))!=(
                'input','number',label,True,True,initial,'native_associated_label',minval,'',step):
            raise ValueError('Mortgage observed input role, limits or initial value changed')
        inputs.append({'selector':selector,'label':label,'value':value})
    b=by_id[submit]
    if (b.get('tag'),b.get('type'),b.get('label'),b.get('visible'),b.get('enabled'))!=('button','button','立即计算',True,True):
        raise ValueError('Mortgage actual calculate control changed')
    rate=widget.get('fixed_rate',{})
    if (rate.get('selector'),rate.get('tag'),rate.get('type'),rate.get('label'),rate.get('value'),rate.get('visible'),rate.get('enabled'),rate.get('label_source'))!=(
            '#interestRate','input','number','年利率（%）','3.05',True,True,'native_associated_label'):
        raise ValueError('Mortgage fixed observed annual rate changed')
    if widget.get('loan_mode')!={'selector':'#loanModeGroup button[data-mode="normal"]','value':'normal','label':'商业贷款','visible':True,'selected':True}:
        raise ValueError('Mortgage commercial mode changed')
    if widget.get('repayment')!={'selector':'#repaymentType','value':'equalPayment','label':'还款方式','display':'等额本息','visible':True,'enabled':True}:
        raise ValueError('Mortgage equal-payment setting changed')
    if (widget.get('result_selector'),widget.get('result_heading'),widget.get('result_initially_visible'))!=('#resultContainer','还款概览',False):
        raise ValueError('Mortgage initial summary must be the observed hidden prospective result')
    for selector,label in [('#monthlyPayment','月供'),('#totalPayment','总还款'),('#totalInterest','总利息')]:
        targets=[x for x in page['result_targets'] if x['selector']==selector]
        if len(targets)!=1 or (targets[0].get('text'),targets[0].get('visible'),targets[0].get('label'),targets[0].get('business_label'),targets[0].get('unit'))!=(
                '0.00 元',False,label,'房贷等额本息','元'):
            raise ValueError('Mortgage result target, role, unit or initial state changed')
    return inputs


def loan_spec(capability,page,widget,strategy_version):
    inputs=validate_observation(capability,page,widget)
    oracle=equal_payment_oracle('12','3.05','1')
    results=[{'selector':'#'+rid,'label':label,'text':oracle[key]+' 元','amount':oracle[key]}
             for rid,label,key in [('monthlyPayment','月供','monthly_payment'),('totalPayment','总还款','total_payment'),
                                    ('totalInterest','总利息','total_interest')]]
    return {'page_uri':URI,'form_label':'房贷计算器','widget_adapter':ADAPTER_ID,
      'goal':'在「房贷计算器」中，以商业贷款、年利率3.05%、等额本息方式，计算贷款金额12万元、期限1年的还款情况，点击「立即计算」并核对月供、总还款和总利息。',
      'inputs':inputs,'submit':{'selector':'button[onclick="calculateMortgage()"]','label':'立即计算'},
      'completion':{'selector':'#monthlyPayment','contains':results[0]['text'],
                    'description':'月供10165.98元，总还款121991.73元，总利息1991.73元'},
      'results':results,'deterministic_strategy':{'id':STRATEGY_ID,'version':strategy_version,
        'business_goal':'固定利率商业房贷等额本息还款计算','operator':'P*r*(1+r)^n/((1+r)^n-1)',
        'principal_yuan':'120000.00','annual_rate_percent':'3.05','months':12,'observed_roles':['贷款金额（万元）','贷款期限（年）'],
        'oracle':oracle,'expected_unit':'元','assurance':'Independent Decimal annuity calculation and month-by-month schedule check; three exact two-decimal observed values and original-frame review required'}}


def verify_loan_summary(actual):
    """Exact visible text contract for this one calibrated fixed mortgage task."""
    oracle=equal_payment_oracle('12','3.05','1')
    expected={rid:oracle[key]+' 元' for rid,key in [('monthlyPayment','monthly_payment'),('totalPayment','total_payment'),('totalInterest','total_interest')]}
    return isinstance(actual,dict) and actual==expected


def compile_loan(capability,spec,task_version=ADAPTER_ID + '-compiler'):
    from .planning import object_sha256
    from .collect import validate_plan
    from .task_contract import validate_m4_task
    from .task_instruction import validate_task_instruction
    pages=[p for p in capability['capabilities'] if p['page_uri']==spec['page_uri']]
    if len(pages)!=1:raise ValueError('Mortgage must bind one observed page')
    page=pages[0];widgets=[w for w in page.get('widgets',[]) if w.get('adapter_id')==ADAPTER_ID]
    if len(widgets)!=1:raise ValueError('Mortgage must bind one observed widget')
    if loan_spec(capability,page,widgets[0],spec['deterministic_strategy']['version'])!=spec:
        raise ValueError('Mortgage specification changed from observed fixed strategy')
    ops=[];subgoals=[]
    for n,request in enumerate(spec['inputs'],1):
        sid='field-'+str(n);selector=request['selector'];label=request['label'];value=request['value']
        common={'subgoal_id':sid,'selector':selector,'evidence':{'target_label':label}}
        ops.append({**common,'operation_id':sid+'-focus','action_type':'click','goal':'选中「'+label+'」',
          'rationale':'填写该项前先聚焦输入位置','expected':'光标进入「'+label+'」'})
        ops.append({'operation_id':sid+'-select','subgoal_id':sid,'action_type':'hotkey','arguments':{'keys':['meta','a']},
          'goal':'选中当前输入内容','rationale':'原输入已有内容，需要整体替换','expected':'当前输入内容被选中'})
        ops.append({**common,'operation_id':sid+'-type','action_type':'type','arguments':{'text':value},
          'goal':'将「'+label+'」填写为「'+value+'」','rationale':'填写任务要求的必要贷款条件','expected':'输入框显示「'+value+'」',
          'postconditions':[{'selector':selector,'value':value}]})
        subgoals.append({'id':sid,'description':'填写「'+label+'」','evidence':[{'operation_id':sid+'-type','postcondition_index':0}]})
    assertions=[]
    for result in spec['results']:
        amount=Decimal(result['amount'])
        assertions.extend([{'selector':result['selector'],'contains':result['text']},
          {'selector':result['selector'],'numbers':{'count':1,'minimum':float(amount),'maximum_exclusive':float(amount+Decimal('0.01'))}},
          {'selector':'#resultContainer p:has(+ '+result['selector']+')','contains':result['label']}])
    assertions.extend([{'selector':'#resultContainer .card-title','contains':'还款概览'},
      {'selector':'#interestRate','value':'3.05'},{'selector':'#repaymentType','value':'equalPayment'},
      {'selector':'#loanModeGroup button.active[data-mode="normal"]','contains':'商业贷款'}])
    ops.append({'operation_id':'calculate','subgoal_id':'result','action_type':'click','selector':spec['submit']['selector'],
      'evidence':{'target_label':'立即计算'},'goal':'点击「立即计算」','rationale':'根据贷款金额、年限和既定利率计算等额本息还款',
      'expected':spec['completion']['description'],'postconditions':assertions})
    subgoals.append({'id':'result','description':'核对月供、总还款和总利息','evidence':[{'final_assertion_index':n} for n in (0,3,6)]})
    task={'task_id':'mortgage-'+object_sha256({'capability':capability['capability_id'],'spec':spec})[:24],
      'task_version':task_version,'capability_id':capability['capability_id'],'capability_version':capability['version'],
      'task_family':'form-workflow','site_uri':capability['site_uri'],'site_category':capability['site_category'],
      'initial_url':URI,'app_name':page['title'],'instruction':spec['goal'],'task_type':['填写表单'],
      'stop_when_final':True,'content_preparation':False,'operations':ops,'subgoals':subgoals,
      'required_actions':[o['operation_id'] for o in ops],'final_assertions':assertions,
      'final_result':spec['completion']['description'],'completion_judgement':'核对最终原图中三个结果名称、金额与元单位均完整显示。',
      'deterministic_strategy':spec['deterministic_strategy'],'capability_screen_status':capability['status'],
      'capability_review_required':capability['status']!='ready'}
    validate_task_instruction(task['instruction']);validate_plan({'tasks':[task]});validate_m4_task(task)
    return task
