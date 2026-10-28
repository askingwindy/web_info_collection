"""Narrow adapter for the observed Lddgo civil-date difference calculator.

This reads existing controls only. A hidden empty result is a prospective target,
never evidence of success: collection must assert it in the saved final frame.
"""
from datetime import date
from urllib.parse import urlsplit

ADAPTER_ID = 'lddgo-date-difference-widget-1'
STRATEGY_ID = 'civil-date-difference-v1'
URI = 'https://www.lddgo.net/common/date'


def matches_uri(uri):
    return urlsplit(uri) == urlsplit(URI)


DATE_INVENTORY_JS = r'''() => {
 const empty={widgets:[],result_targets:[],widget_rejections:[]};
 if(location.href!=='https://www.lddgo.net/common/date')return empty;
 const id='lddgo-date-difference-widget-1',clean=s=>(s||'').replace(/\s+/g,' ').trim();
 const fail=reason=>({...empty,widget_rejections:[{adapter_id:id,page_uri:location.href,reason}]});
 const one=s=>document.querySelectorAll(s).length===1?document.querySelector(s):null;
 const visible=e=>{if(!e||!e.checkVisibility({checkOpacity:true,checkVisibilityCSS:true}))return false;const r=e.getBoundingClientRect();
  const hit=document.elementFromPoint((r.left+r.right)/2,(r.top+r.bottom)/2);
  return r.width>0&&r.height>0&&r.left>=0&&r.top>=0&&r.right<=innerWidth&&r.bottom<=innerHeight&&!!hit&&(hit===e||e.contains(hit));};
 const first=one('#date1'),last=one('#date2'),button=one('#startCalculate'),result=one('#betweenDay');
 if(!first||!last||!button||!result)return fail('Missing or ambiguous date controls/result');
 const card=first.closest('.layui-card');
 if(!card||!card.contains(last)||!card.contains(button)||!card.contains(result)||
    clean(card.querySelector('.layui-card-header')?.innerText)!=='相差天数计算')return fail('Date business grouping changed');
 const editable=[...card.querySelectorAll('input:not([readonly]),textarea,select,button')];
 if(editable.length!==3||editable.some(e=>![first,last,button].includes(e)))return fail('Date widget has extra/missing business controls');
 const fields=[];
 for(const [el,label] of [[first,'开始日期'],[last,'结束日期']]){
  const observed=el.closest('.layui-form-item')?.querySelector('.layui-form-label');
  if(el.localName!=='input'||el.type!=='text'||el.readOnly||el.disabled||!visible(el)||
     !observed||!visible(observed)||clean(observed.innerText)!==label||!/^\d{4}-\d{2}-\d{2}$/.test(el.value))
   return fail('Date role, format or viewport visibility changed');
  fields.push({selector:'#'+el.id,tag:'input',type:'text',label,visible:true,enabled:true,value:el.value,
   label_source:'same_form_item_label',min:'',max:'',options:[]});
 }
 if(button.localName!=='button'||!['submit','button'].includes(button.type)||button.disabled||!visible(button)||clean(button.innerText)!=='计算'||
    result.localName!=='input'||!result.readOnly||result.type!=='text'||!result.closest('#resultContainer')||
    clean(result.closest('.layui-form-item')?.querySelector('.layui-form-label')?.innerText)!=='相差')
   return fail('Date submit or readonly result binding changed');
 fields.push({selector:'#startCalculate',tag:'button',type:button.type,label:'计算',visible:true,enabled:true,value:''});
 return {widgets:[{kind:'non-form-widget',adapter_id:id,page_uri:location.href,label:'相差天数计算',fields,
    result_selector:'#betweenDay',result_label:'相差',result_label_selector:'#resultContainer .layui-form-item:first-child .layui-form-label'}],
  result_targets:[{selector:'#betweenDay',text:result.value,value:result.value,visible:visible(result),readonly:true,
    label:'相差',business_label:'日期相差天数'}],widget_rejections:[]};
}'''


def date_spec(capability, page, widget, strategy_version):
    if not all(matches_uri(u) for u in (capability['site_uri'], page['page_uri'], widget.get('page_uri', ''))):
        raise ValueError('Date strategy requires its exact observed URI')
    if (widget.get('kind'), widget.get('adapter_id'), widget.get('label')) != ('non-form-widget', ADAPTER_ID, '相差天数计算'):
        raise ValueError('Date widget binding changed')
    fields = widget['fields']
    if len(fields) != 3 or {x['selector'] for x in fields} != {'#date1', '#date2', '#startCalculate'}:
        raise ValueError('Date strategy requires its two distinct date roles and submit')
    by_id = {x['selector']: x for x in fields}
    inputs = []
    for selector, label, value in (('#date1', '开始日期', '2024-02-28'), ('#date2', '结束日期', '2024-03-01')):
        f = by_id[selector]
        if (f.get('tag'), f.get('type'), f.get('label'), f.get('visible'), f.get('enabled'), f.get('label_source')) != (
                'input', 'text', label, True, True, 'same_form_item_label'):
            raise ValueError('Date observed input role/visibility changed')
        if date.fromisoformat(f['value']).isoformat() != f['value']:
            raise ValueError('Date observed input must use the exact YYYY-MM-DD format')
        if f['value'] == value:
            raise ValueError('Date input already requested; do not add redundant actions')
        inputs.append({'selector': selector, 'label': label, 'value': value})
    button = by_id['#startCalculate']
    if (button.get('tag'), button.get('label'), button.get('visible'), button.get('enabled')) != ('button', '计算', True, True) or button.get('type') not in ('button', 'submit'):
        raise ValueError('Date calculate control changed')
    if (widget.get('result_selector'), widget.get('result_label'), widget.get('result_label_selector')) != (
            '#betweenDay', '相差', '#resultContainer .layui-form-item:first-child .layui-form-label'):
        raise ValueError('Date result role changed')
    results = [x for x in page['result_targets'] if x['selector'] == '#betweenDay']
    if len(results) != 1 or results[0].get('readonly') is not True or (
            results[0].get('label'), results[0].get('business_label')) != ('相差', '日期相差天数'):
        raise ValueError('Date readonly result evidence missing')
    days = (date.fromisoformat(inputs[1]['value']) - date.fromisoformat(inputs[0]['value'])).days
    return {'page_uri': page['page_uri'], 'form_label': widget['label'], 'widget_adapter': ADAPTER_ID,
        'goal': '在「日期计算器」的「相差天数计算」中，将开始日期填写为2024-02-28、结束日期填写为2024-03-01，点击「计算」并核对两日期相差2天。',
        'inputs': inputs, 'submit': {'selector': '#startCalculate', 'label': '计算'},
        'completion': {'selector': '#betweenDay', 'number': days, 'description': '两日期相差2天'},
        'deterministic_strategy': {'id': STRATEGY_ID, 'version': strategy_version,
            'business_goal': '两个公历日期间的天数差', 'operator': 'civil_end_date-civil_start_date',
            'observed_roles': [x['label'] for x in inputs], 'expected_unit': '天',
            'assurance': 'Python civil-date arithmetic proposal; saved visible result and independent review required'}}
