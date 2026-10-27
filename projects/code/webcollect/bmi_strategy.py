"""Read-only adapter for the observed public Jyshare BMI numeric widget.

This is a non-form widget with two number/range pairs. The ranges are observed
as linked controls, never mistaken for extra independent business inputs. The
adapter neither changes the page nor grants visual/QC approval.
"""
from decimal import Decimal, ROUND_HALF_UP
from urllib.parse import urlsplit

ADAPTER_ID = 'jyshare-bmi-widget-1'
STRATEGY_ID = 'body-mass-index-v1'
BMI_URI = 'https://www.jyshare.com/front-end/9428/'


def matches_uri(uri):
    parsed = urlsplit(uri)
    return (parsed.scheme == 'https' and parsed.netloc == 'www.jyshare.com' and
            parsed.path.rstrip('/') == '/front-end/9428' and not parsed.query and not parsed.fragment)


# The page and selectors below were observed on the real public page. All
# coordinates, visibility, labels, input limits and initial values are read
# afresh. No form or control is added to the DOM by this inventory function.
BMI_INVENTORY_JS = r'''() => {
 const empty={widgets:[],result_targets:[],widget_rejections:[]};
 const uri=new URL(location.href);
 if(uri.protocol!=='https:'||uri.host!=='www.jyshare.com'||
    uri.pathname.replace(/\/$/,'')!=='/front-end/9428'||uri.search||uri.hash)return empty;
 const clean=s=>(s||'').replace(/\s+/g,' ').trim();
 const fail=reason=>({...empty,widget_rejections:[{adapter_id:'jyshare-bmi-widget-1',page_uri:location.href,reason}]});
 const one=(selector,root=document)=>{const values=root.querySelectorAll(selector);return values.length===1?values[0]:null;};
 const visible=e=>{
   if(!e||!e.checkVisibility({checkOpacity:true,checkVisibilityCSS:true}))return false;
   const r=e.getBoundingClientRect();
   if(r.width<=0||r.height<=0||r.left<0||r.top<0||r.right>innerWidth||r.bottom>innerHeight)return false;
   const hit=document.elementFromPoint((r.left+r.right)/2,(r.top+r.bottom)/2);
   return !!hit&&(hit===e||e.contains(hit));
 };
 const height=one('#heightInput'),weight=one('#weightInput'),button=one('#calculateBtn'),result=one('#bmiValue');
 if(!height||!weight||!button||!result)return fail('BMI requires unique observed inputs, calculate button and result');
 const root=height.closest('.form-row');
 if(!root||root!==weight.closest('.form-row')||!root.contains(button)||!root.contains(result)||
    height.form||weight.form||button.form)return fail('BMI non-form widget grouping changed');
 const all=[...root.querySelectorAll('input,textarea,select,button,[contenteditable=true]')];
 const ids=['height','heightInput','weight','weightInput','calculateBtn'];
 if(all.length!==ids.length||all.some(e=>!ids.includes(e.id)))return fail('BMI widget has additional or missing controls');
 const fields=[],linked=[];
 for(const [input,role,unit,sliderId] of [[height,'身高','cm','height'],[weight,'体重','kg','weight']]){
   const group=input.closest('.input-group'),formGroup=input.closest('.form-group');
   const label=group&&one('.input-group-text',group),slider=one('#'+sliderId);
   const sliderLabel=formGroup&&one('label[for="'+sliderId+'"]',formGroup);
   const expected=role+' ('+unit+')';
   if(input.localName!=='input'||input.type!=='number'||input.disabled||input.readOnly||!visible(input)||
      !label||!visible(label)||clean(label.innerText)!==expected||!formGroup||!formGroup.contains(group)||
      !slider||slider.type!=='range'||!formGroup.contains(slider)||!visible(slider)||slider.disabled||
      !sliderLabel||!visible(sliderLabel)||clean(sliderLabel.innerText)!==expected||
      slider.value!==input.value||slider.min!==input.min||slider.max!==input.max)
     return fail('BMI numeric role, visible unit label or linked slider evidence changed');
   fields.push({selector:'#'+input.id,tag:'input',type:'number',name:input.name||'',label:clean(label.innerText),
     role,unit,visible:true,enabled:true,min:input.min,max:input.max,value:input.value,options:[],
     label_source:'same_input_group_text',label_selector:'.input-group:has(> #'+input.id+') .input-group-text'});
   linked.push({selector:'#'+sliderId,type:'range',label:clean(sliderLabel.innerText),visible:true,
     value:slider.value,min:slider.min,max:slider.max,linked_input:'#'+input.id});
 }
 const resultContainer=one('#resultContainer'),heading=resultContainer&&one('h2',resultContainer);
 const unit=result.nextElementSibling;
 if(button.localName!=='button'||button.disabled||!visible(button)||clean(button.innerText)!=='计算 BMI'||
    !resultContainer||!resultContainer.contains(result)||!visible(result)||!heading||!visible(heading)||
    clean(heading.innerText)!=='您的 BMI 结果'||!unit||!visible(unit)||clean(unit.innerText)!=='BMI')
   return fail('BMI calculate control or visible result and business label changed');
 fields.push({selector:'#calculateBtn',tag:'button',type:button.type,label:clean(button.innerText),
   visible:true,enabled:true,name:'',value:'',min:'',max:'',options:[]});
 const widget={kind:'non-form-widget',adapter_id:'jyshare-bmi-widget-1',label:'BMI 计算器',
   page_uri:location.href,container_selector:'.form-row',fields,linked_controls:linked,
   result_selector:'#bmiValue',result_label:'您的 BMI 结果',result_label_selector:'#resultContainer h2',
   result_business_label:'BMI',display_precision:1};
 return {widgets:[widget],result_targets:[{selector:'#bmiValue',text:clean(result.innerText),visible:true,
   label:'您的 BMI 结果',business_label:'BMI'}],widget_rejections:[]};
}'''


def bmi_spec(capability, page, widget, strategy_version):
    """Validate the typed observation and produce one independently computed task."""
    if not all(matches_uri(uri) for uri in (capability['site_uri'], page['page_uri'], widget['page_uri'])):
        raise ValueError('BMI strategy only supports its observed public page')
    if (widget.get('kind'), widget.get('adapter_id'), widget.get('label')) != (
            'non-form-widget', ADAPTER_ID, 'BMI 计算器'):
        raise ValueError('BMI requires its typed non-form widget observation')
    fields = widget['fields']
    if len(fields) != 3 or len({field['selector'] for field in fields}) != 3:
        raise ValueError('BMI requires exactly two numeric fields and its calculate button')
    observed = {field['selector']: field for field in fields}
    sliders = widget.get('linked_controls', [])
    if len(sliders) != 2 or len({field['selector'] for field in sliders}) != 2:
        raise ValueError('BMI requires exactly two linked slider observations')
    inputs = []
    for selector, slider, role, unit, value, minimum in (
            ('#heightInput', '#height', '身高', 'cm', '160', '1'),
            ('#weightInput', '#weight', '体重', 'kg', '64', '10')):
        field = observed.get(selector, {})
        linked = next((item for item in sliders if item['selector'] == slider), {})
        label = role+' ('+unit+')'
        if (field.get('tag'), field.get('type'), field.get('label'), field.get('role'), field.get('unit'),
                field.get('visible'), field.get('enabled'), field.get('label_source')) != (
                'input', 'number', label, role, unit, True, True, 'same_input_group_text'):
            raise ValueError('BMI numeric role or visible unit evidence missing')
        if (field.get('min'), field.get('max')) != (minimum, '290'):
            raise ValueError('BMI observed input limits changed')
        if (linked.get('linked_input'), linked.get('type'), linked.get('label'), linked.get('visible'),
                linked.get('value'), linked.get('min'), linked.get('max')) != (
                selector, 'range', label, True, field['value'], field['min'], field['max']):
            raise ValueError('BMI linked slider does not agree with the numeric field')
        initial = Decimal(field['value'])
        if not initial.is_finite() or not Decimal(minimum) <= initial <= Decimal('290'):
            raise ValueError('BMI initial input is outside its observed limits')
        if initial == Decimal(value):
            raise ValueError('BMI requested input is already present; no unnecessary input actions')
        inputs.append({'selector':selector, 'label':label, 'value':value})
    button = observed.get('#calculateBtn', {})
    if (button.get('tag'), button.get('label'), button.get('visible'), button.get('enabled')) != (
            'button', '计算 BMI', True, True) or button.get('type') not in ('button', 'submit'):
        raise ValueError('BMI calculate button evidence changed')
    if (widget.get('result_selector'), widget.get('result_label'), widget.get('result_label_selector'),
            widget.get('result_business_label'), widget.get('display_precision')) != (
            '#bmiValue', '您的 BMI 结果', '#resultContainer h2', 'BMI', 1):
        raise ValueError('BMI result label or display precision changed')
    results = [target for target in page['result_targets'] if target['selector'] == '#bmiValue']
    if len(results) != 1 or results[0].get('visible') is not True or (
            results[0].get('label'), results[0].get('business_label')) != ('您的 BMI 结果', 'BMI'):
        raise ValueError('BMI result must be a unique visible numeric target with business label')
    actual = results[0]['text']
    initial_bmi = Decimal(observed['#weightInput']['value']) / (Decimal(observed['#heightInput']['value']) / 100) ** 2
    if actual != format(initial_bmi.quantize(Decimal('0.1'), rounding=ROUND_HALF_UP), '.1f'):
        raise ValueError('BMI initial result does not match its observed inputs and one-decimal display')
    expected = Decimal(inputs[1]['value']) / (Decimal(inputs[0]['value']) / 100) ** 2
    if expected != expected.to_integral_value():
        raise ValueError('This BMI task requires an exact integer numeric oracle')
    display = format(expected, '.1f')
    if Decimal(actual) == expected:
        raise ValueError('BMI result already complete before actions')
    return {'page_uri':page['page_uri'], 'form_label':widget['label'], 'widget_adapter':ADAPTER_ID,
        'goal':'在「BMI 计算器」中将身高填写为160厘米、体重填写为64千克，点击「计算 BMI」，核对计算结果为25.0。',
        'inputs':inputs, 'submit':{'selector':'#calculateBtn', 'label':'计算 BMI'},
        'completion':{'selector':'#bmiValue', 'number':int(expected), 'description':'BMI 计算结果为'+display},
        'deterministic_strategy':{'id':STRATEGY_ID, 'version':strategy_version, 'business_goal':'BMI 数值计算',
            'operator':'weight_kg/(height_cm/100)^2', 'expected_display':display,
            'observed_roles':[item['label'] for item in inputs],
            'assurance':'observed public widget; arithmetic test only; saved-frame assertions and independent QC still required'}}
