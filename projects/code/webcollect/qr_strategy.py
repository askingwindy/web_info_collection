"""Narrow WiFi QR strategy and independent original-PNG pixel oracle.

The oracle decodes saved PNG pixels with the installed macOS Vision framework.
It does not read a canvas data URL, browser state, website serializer, or DOM
payload. A detected code still needs the task's visible input and geometry checks.
"""
from urllib.parse import urlsplit
from .qr_pixel import decode_qr_png, verify_qr_png

ADAPTER_ID='jyshare-wifi-qr-widget-1'
STRATEGY_ID='wifi-qr-generation-v1'
URI='https://www.jyshare.com/front-end/3454/'
SSID='示例网络'
PASSWORD='12345678'


def matches_uri(uri):
    return urlsplit(uri)==urlsplit(URI)


def wifi_payload(ssid,password,encryption='WPA',hidden=False):
    """A bounded synthetic WPA WiFi serialization, with explicit escaping."""
    if (not isinstance(ssid,str) or not ssid or len(ssid.encode('utf-8'))>32 or
        not isinstance(password,str) or not 8<=len(password)<=63 or
        any(ord(c)<32 for c in ssid+password) or encryption!='WPA' or type(hidden) is not bool):
        raise ValueError('Unsupported WiFi parameters')
    escape=lambda value:''.join('\\'+c if c in '\\;,:"' else c for c in value)
    return 'WIFI:T:'+encryption+';S:'+escape(ssid)+';P:'+escape(password)+';'+('H:true;' if hidden else '')+';'


QR_INVENTORY_JS=r'''() => {
 const empty={widgets:[],result_targets:[],widget_rejections:[]};
 if(location.href!=='https://www.jyshare.com/front-end/3454/')return empty;
 const id='jyshare-wifi-qr-widget-1',clean=s=>(s||'').replace(/\s+/g,' ').trim();
 const fail=reason=>({...empty,widget_rejections:[{adapter_id:id,page_uri:location.href,reason}]});
 const one=s=>document.querySelectorAll(s).length===1?document.querySelector(s):null;
 const shown=e=>!!e&&e.checkVisibility({checkOpacity:true,checkVisibilityCSS:true});
 const bounds=e=>{const r=e.getBoundingClientRect();return r.width>0&&r.height>0&&r.left>=0&&r.top>=0&&r.right<=innerWidth&&r.bottom<=innerHeight;};
 const visible=e=>{if(!shown(e)||!bounds(e))return false;const r=e.getBoundingClientRect(),h=document.elementFromPoint((r.left+r.right)/2,(r.top+r.bottom)/2);return !!h&&(h===e||e.contains(h));};
 const root=one('#rn-qr-tool'),tabs=one('#rnqr-typeTabs'),entry=one('#rnqr-typeTabs button[data-type="wifi"]');
 const text=one('#rnqr-text-content'),form=one('.rnqr-form[data-form="wifi"]'),canvas=one('#rnqr-qrCanvas'),cover=one('#rnqr-qrEmpty');
 if(!root||root.dataset.initialized!=='1'||!tabs||!entry||!text||!form||!canvas||!cover||
    ![tabs,entry,text,form,canvas,cover].every(e=>root.contains(e)))return fail('QR unique observed root/control grouping changed');
 const types=['text','wifi','vcard','email','sms','tel','geo','event'],buttons=[...tabs.querySelectorAll('button')];
 if(buttons.length!==8||buttons.some((b,n)=>b.dataset.type!==types[n]||b.classList.contains('rnqr-active')!==(n===0)||b.disabled))
   return fail('QR initial type tabs changed');
 if(!visible(entry)||clean(entry.innerText)!=='WiFi'||entry.type!=='button'||text.value!==''||!visible(text)||shown(form)||
    !text.closest('.rnqr-form[data-form="text"]')?.classList.contains('rnqr-active'))return fail('QR initial text type or WiFi activation changed');
 const fields=[];
 for(const [rid,label,placeholder] of [['rnqr-wifi-ssid','网络名称 SSID','MyWiFi'],['rnqr-wifi-pass','密码','无密码网络请选择“无密码”']]){
   const e=one('#'+rid),labels=[...(e?.labels||[])];
   if(!e||!form.contains(e)||e.localName!=='input'||e.type!=='text'||e.value!==''||e.disabled||e.readOnly||shown(e)||
      e.placeholder!==placeholder||labels.length!==1||labels[0]!==e.parentElement||clean(labels[0].querySelector(':scope > span')?.textContent)!==label)
      return fail('QR prospective native WiFi input role changed');
   fields.push({selector:'#'+rid,tag:'input',type:'text',label,value:'',visible:false,enabled:true,
      label_source:'native_wrapping_label',state:'inactive_prospective',activation_selector:'#rnqr-typeTabs button[data-type="wifi"]',placeholder});
 }
 const enc=one('#rnqr-wifi-enc'),hidden=one('#rnqr-wifi-hidden');
 if(!enc||!hidden||!form.contains(enc)||!form.contains(hidden)||enc.value!=='WPA'||enc.disabled||
   enc.options.length!==3||[...enc.options].map(o=>o.value).join('|')!=='WPA|WEP|nopass'||
   hidden.type!=='checkbox'||hidden.checked||hidden.disabled||shown(enc)||shown(hidden)||
   form.querySelectorAll('input,textarea,select,button,[contenteditable=true]').length!==4)
   return fail('QR original WiFi settings or control set changed');
 if(canvas.localName!=='canvas'||canvas.width!==320||canvas.height!==320||!bounds(canvas)||!visible(cover)||
    clean(cover.innerText)!=='请填写内容以生成二维码'||one('#rnqr-statChars')?.textContent.trim()!=='—'||
    one('#rnqr-historyCount')?.textContent.trim()!=='0'||one('.rnqr-style-panel')?.open)
   return fail('QR empty initial preview or original settings changed');
 return {widgets:[{kind:'non-form-widget',adapter_id:id,page_uri:location.href,label:'在线二维码生成器',fields,
   activation:{selector:'#rnqr-typeTabs button[data-type="wifi"]',label:'WiFi',tag:'button',type:'button',visible:true,enabled:true},
   initial_type:'text',fixed_settings:{encryption:'WPA',hidden:false},canvas:{selector:'#rnqr-qrCanvas',width:320,height:320,
   initial_overlay:'请填写内容以生成二维码',fully_in_viewport:true},viewport:[innerWidth,innerHeight],observed_scroll_y:scrollY}],
   result_targets:[{selector:'#rnqr-qrCanvas',label:'二维码预览',kind:'qr_canvas',visible:false,state:'covered_empty_preview'}],widget_rejections:[]};
}'''


def validate_observation(capability,page,widget):
    if not all(matches_uri(uri) for uri in (capability['site_uri'],page['page_uri'],widget.get('page_uri',''))):
        raise ValueError('QR requires its exact observed URI')
    if (widget.get('kind'),widget.get('adapter_id'),widget.get('label'),widget.get('initial_type'),widget.get('viewport'),widget.get('observed_scroll_y'))!=(
            'non-form-widget',ADAPTER_ID,'在线二维码生成器','text',[1280,720],0):
        raise ValueError('QR observed identity, type or viewport changed')
    activation={'selector':'#rnqr-typeTabs button[data-type="wifi"]','label':'WiFi','tag':'button','type':'button','visible':True,'enabled':True}
    if widget.get('activation')!=activation or widget.get('fixed_settings')!={'encryption':'WPA','hidden':False}:
        raise ValueError('QR visible activation control or fixed settings changed')
    fields=widget.get('fields',[])
    if len(fields)!=2:raise ValueError('QR requires exactly two WiFi input roles')
    inputs=[]
    for selector,label,placeholder,value in [('#rnqr-wifi-ssid','网络名称 SSID','MyWiFi',SSID),('#rnqr-wifi-pass','密码','无密码网络请选择“无密码”',PASSWORD)]:
        found=[f for f in fields if f.get('selector')==selector]
        expected={'selector':selector,'tag':'input','type':'text','label':label,'value':'','visible':False,'enabled':True,
                  'label_source':'native_wrapping_label','state':'inactive_prospective','activation_selector':activation['selector'],'placeholder':placeholder}
        if len(found)!=1 or found[0]!=expected:raise ValueError('QR prospective input binding changed')
        inputs.append({'selector':selector,'label':label,'value':value})
    if widget.get('canvas')!={'selector':'#rnqr-qrCanvas','width':320,'height':320,'initial_overlay':'请填写内容以生成二维码','fully_in_viewport':True}:
        raise ValueError('QR prospective canvas changed')
    targets=[r for r in page['result_targets'] if r.get('selector')=='#rnqr-qrCanvas']
    if targets!=[{'selector':'#rnqr-qrCanvas','label':'二维码预览','kind':'qr_canvas','visible':False,'state':'covered_empty_preview'}]:
        raise ValueError('QR initially covered canvas must not be treated as decoded result')
    return inputs


def qr_spec(capability,page,widget,strategy_version):
    inputs=validate_observation(capability,page,widget);payload=wifi_payload(SSID,PASSWORD)
    return {'page_uri':URI,'form_label':'在线二维码生成器','widget_adapter':ADAPTER_ID,
        'goal':'在「在线二维码生成器」中选择「WiFi」，为示例网络生成二维码：网络名称填写「示例网络」，示例密码填写「12345678」，保留WPA加密和非隐藏网络，查看生成的完整二维码。',
        'inputs':inputs,'activation':widget['activation'],'completion':{'selector':'#rnqr-qrCanvas','qr_png_payload':payload,
          'description':'二维码已生成，原图解码内容对应示例网络、示例密码12345678及WPA非隐藏网络'},
        'deterministic_strategy':{'id':STRATEGY_ID,'version':strategy_version,'business_goal':'结构化WiFi凭据生成二维码',
          'operator':'wifi-serialization-and-qr-pixel-decode','observed_roles':['网络名称 SSID','密码'],
          'expected_payload':payload,'hidden_serialization':'omit H for unchecked network',
          'assurance':'Requires original saved PNG decode with Apple Vision, exactly one QR inside the observed canvas, and bound visible fields'}}


def validate_qr_assertion_scope(task,condition):
    expected={'selector':'#rnqr-qrCanvas','qr_png_payload':wifi_payload(SSID,PASSWORD)}
    if (condition!=expected or not all(matches_uri(task.get(key,'')) for key in ('initial_url','site_uri')) or
        task.get('deterministic_strategy',{}).get('id')!=STRATEGY_ID):
        raise ValueError('QR pixel assertion requires the exact observed URI, WiFi strategy and fixed synthetic payload')


def compile_qr(capability,spec,task_version='observed-wifi-qr-compiler-1'):
    from .planning import object_sha256
    from .collect import validate_plan
    from .task_contract import validate_m4_task
    from .task_instruction import validate_task_instruction
    pages=[p for p in capability['capabilities'] if p['page_uri']==spec['page_uri']]
    if len(pages)!=1:raise ValueError('QR must bind one observed page')
    page=pages[0];widgets=[w for w in page.get('widgets',[]) if w.get('adapter_id')==ADAPTER_ID]
    if len(widgets)!=1 or qr_spec(capability,page,widgets[0],spec['deterministic_strategy']['version'])!=spec:
        raise ValueError('QR fixed specification changed from its observed widget')
    ops=[{'operation_id':'activate-wifi','subgoal_id':'wifi','action_type':'click','selector':spec['activation']['selector'],
          'evidence':{'target_label':'WiFi'},'goal':'选择「WiFi」二维码类型','rationale':'切换到网络名称和密码输入区域',
          'expected':'显示网络名称、密码与加密方式控件','postconditions':[{'selector':'#rnqr-wifi-ssid','value':''},
          {'selector':'#rnqr-wifi-pass','value':''},{'selector':'#rnqr-wifi-enc','value':'WPA'}]}]
    subgoals=[{'id':'wifi','description':'选择WiFi类型','evidence':[{'operation_id':'activate-wifi','postcondition_index':0}]}]
    for n,item in enumerate(spec['inputs'],1):
        sid='field-'+str(n);common={'subgoal_id':sid,'selector':item['selector'],'evidence':{'target_label':item['label']}}
        ops.append({**common,'operation_id':sid+'-focus','action_type':'click','goal':'选中「'+item['label']+'」',
                    'rationale':'先聚焦空白输入框','expected':'光标进入「'+item['label']+'」'})
        ops.append({**common,'operation_id':sid+'-type','action_type':'type','arguments':{'text':item['value']},
                    'goal':'将「'+item['label']+'」填写为「'+item['value']+'」','rationale':'填写生成该WiFi二维码所需的示例网络参数',
                    'expected':'输入框显示「'+item['value']+'」','postconditions':[{'selector':item['selector'],'value':item['value']}],
                    'execution':{'settle_ms':500}})
        subgoals.append({'id':sid,'description':'填写「'+item['label']+'」','evidence':[{'operation_id':sid+'-type','postcondition_index':0}]})
    assertions=[{'selector':'#rnqr-wifi-ssid','value':SSID},{'selector':'#rnqr-wifi-pass','value':PASSWORD},
        {'selector':'#rnqr-wifi-enc','value':'WPA'},{'selector':'label.rnqr-switch:has(> #rnqr-wifi-hidden)','checked':False},
        {'selector':'#rnqr-typeTabs button.rnqr-active[data-type="wifi"]','contains':'WiFi'},
        {'selector':'#rnqr-qrCanvas','qr_png_payload':wifi_payload(SSID,PASSWORD)}]
    subgoals.append({'id':'result','description':'核对生成的完整二维码','evidence':[{'final_assertion_index':5}]})
    task={'task_id':'wifi-qr-'+object_sha256({'capability':capability['capability_id'],'spec':spec})[:24],
        'task_version':task_version,'capability_id':capability['capability_id'],'capability_version':capability['version'],
        'task_family':'form-workflow','site_uri':URI,'site_category':capability['site_category'],'initial_url':URI,
        'app_name':page['title'],'instruction':spec['goal'],'task_type':['填写表单'],'stop_when_final':True,'content_preparation':False,
        'operations':ops,'subgoals':subgoals,'required_actions':[o['operation_id'] for o in ops],'final_assertions':assertions,
        'final_result':spec['completion']['description'],'completion_judgement':'核对原图中的完整二维码可独立解出要求的示例网络、密码和加密方式。',
        'deterministic_strategy':spec['deterministic_strategy'],'capability_screen_status':capability['status'],
        'capability_review_required':capability['status']!='ready'}
    validate_task_instruction(task['instruction']);validate_plan({'tasks':[task]});validate_m4_task(task)
    return task
