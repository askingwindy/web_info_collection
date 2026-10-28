"""Narrow observed placeholder-image workflow; PNGs require independent review."""
import base64
import hashlib
from io import BytesIO
from urllib.parse import urlsplit

ADAPTER_ID='jyshare-placeholder-widget-1'
STRATEGY_ID='placeholder-image-generation-v1'
URI='https://www.jyshare.com/front-end/9355/'
IMAGE_SELECTOR='#placeholderResult > img.holderjs-placeholder'
EXPECTED_INPUTS=[('#width','宽度','400'),('#height','高度','200'),('#customText','自定义文本','预览图')]
SOURCE_DOM_SHA256='e9f97ee23fa15841c5aadf84e77680f9355b13a3e34dac95a575d7a79e51a4b2'

def matches_uri(uri):return urlsplit(uri)==urlsplit(URI)

PLACEHOLDER_INVENTORY_JS=r'''() => {
 const empty={widgets:[],result_targets:[],widget_rejections:[]};
 if(location.href!=='https://www.jyshare.com/front-end/9355/')return empty;
 const id='jyshare-placeholder-widget-1',clean=s=>(s||'').replace(/\s+/g,' ').trim();
 const fail=reason=>({...empty,widget_rejections:[{adapter_id:id,page_uri:location.href,reason}]});
 const one=(s,r=document)=>r.querySelectorAll(s).length===1?r.querySelector(s):null;
 const visible=e=>{if(!e||!e.checkVisibility({checkOpacity:true,checkVisibilityCSS:true}))return false;
  const r=e.getBoundingClientRect(),h=document.elementFromPoint((r.left+r.right)/2,(r.top+r.bottom)/2);
  return r.width>0&&r.height>0&&r.left>=0&&r.top>=0&&r.right<=innerWidth&&r.bottom<=innerHeight&&!!h&&(h===e||e.contains(h));};
 const width=one('#width'),root=width?.closest('.col-md-6.border'),result=one('#placeholderResult');
 if(!root||!result||root.parentElement!==result.parentElement.parentElement)return fail('Placeholder settings/preview grouping changed');
 const fields=[];
 for(const [sid,type,label] of [['width','number','宽度'],['height','number','高度'],['customText','text','自定义文本']]){
  const e=one('#'+sid),caption=e&&one('label[for="'+sid+'"]',root);
  if(!e||!root.contains(e)||e.localName!=='input'||e.type!==type||e.disabled||e.readOnly||!visible(e)||
     !caption||caption.control!==e||!visible(caption)||clean(caption.innerText)!==label)return fail('Input identity or readable associated label changed');
  fields.push({selector:'#'+sid,tag:'input',type,label,value:e.value,visible:true,enabled:true,label_source:'associated_label'});
 }
 const settings=[];
 for(const [sid,tag,value,label] of [['fontSize','input','24','字体大小'],['fontFamily','select','Arial','选择字体'],['theme','select','gray','选择主题']]){
  const e=one('#'+sid),caption=e&&one('label[for="'+sid+'"]',root);
  if(!e||!root.contains(e)||e.localName!==tag||e.value!==value||e.disabled||!visible(e)||!caption||!visible(caption)||
     clean(caption.innerText)!==label)return fail('Required visible font/theme defaults changed');
  settings.push({selector:'#'+sid,tag,label,value,visible:true,enabled:true});
 }
 const button=one('#generateBtn'),download=one('#downloadImage'),image=one('#placeholderResult > img.holderjs-placeholder');
 if(!button||!download||!root.contains(button)||!root.contains(download)||button.localName!=='button'||button.disabled||
    !visible(button)||clean(button.innerText)!=='生成占位图'||clean(download.innerText)!=='下载图片')return fail('Generate/download identity changed');
 const custom=one('#customerThemeSet');
 if(!custom||custom.checkVisibility({checkOpacity:true,checkVisibilityCSS:true})||root.querySelectorAll('input,select,button,textarea').length!==10)
  return fail('Expected six settings, two hidden colors and two buttons');
 if(!image||result.children.length!==1||!visible(image)||!image.complete||!image.naturalWidth||!image.src.startsWith('data:image/png;base64,'))
  return fail('Expected one fully visible decoded PNG preview');
 const r=image.getBoundingClientRect();
 fields.push({selector:'#generateBtn',tag:'button',type:button.type,label:'生成占位图',value:'',visible:true,enabled:true});
 return {widgets:[{kind:'non-form-widget',adapter_id:id,page_uri:location.href,label:'在线占位图生成工具',fields,settings,
  result_selector:'#placeholderResult > img.holderjs-placeholder',viewport:[innerWidth,innerHeight],observed_scroll_y:scrollY}],
  result_targets:[{selector:'#placeholderResult > img.holderjs-placeholder',tag:'img',visible:true,complete:true,
   natural_width:image.naturalWidth,natural_height:image.naturalHeight,src:image.src,holder_source:image.getAttribute('data-src'),
   alt:image.alt,rect:[r.left,r.top,r.right,r.bottom]}],widget_rejections:[]};
}'''

def validate_observation(capability,page,widget):
    if not all(matches_uri(u) for u in [capability['site_uri'],page['page_uri'],widget.get('page_uri','')]):raise ValueError('Placeholder requires exact URI')
    if (widget.get('adapter_id'),widget.get('label'),widget.get('viewport'),widget.get('observed_scroll_y'))!=(ADAPTER_ID,'在线占位图生成工具',[1280,720],0):raise ValueError('Placeholder identity or viewport changed')
    fields=widget.get('fields',[])
    expected=[('#width','number','宽度','300'),('#height','number','高度','300'),('#customText','text','自定义文本','300X300')]
    if len(fields)!=4:raise ValueError('Expected three requested inputs and generate')
    for field,(selector,kind,label,value) in zip(fields,expected):
        if any(field.get(k)!=v for k,v in {'selector':selector,'tag':'input','type':kind,'label':label,'value':value,'visible':True,'enabled':True,'label_source':'associated_label'}.items()):raise ValueError('Observed initial input changed')
    if any(fields[3].get(k)!=v for k,v in {'selector':'#generateBtn','tag':'button','label':'生成占位图','visible':True,'enabled':True}.items()):raise ValueError('Generate control changed')
    settings=widget.get('settings',[])
    if [(s.get('selector'),s.get('tag'),s.get('label'),s.get('value'),s.get('visible'),s.get('enabled')) for s in settings]!=[
        ('#fontSize','input','字体大小','24',True,True),('#fontFamily','select','选择字体','Arial',True,True),('#theme','select','选择主题','gray',True,True)]:raise ValueError('Font/theme defaults changed')
    results=page.get('result_targets',[])
    if len(results)!=1 or results[0].get('holder_source')!='holder.js/300x300?size=24&theme=gray&text=300X300&font=Arial':raise ValueError('Initial preview changed')
    return development_operations()

def development_operations():
    operations=[]
    for index,(selector,label,value) in enumerate(EXPECTED_INPUTS,1):
        common={'selector':selector,'evidence':{'target_label':label},'subgoal_id':'field-'+str(index)}
        operations.extend([{**common,'operation_id':f'field-{index}-focus','action_type':'click','goal':'选中「'+label+'」'},
          {'operation_id':f'field-{index}-select','subgoal_id':'field-'+str(index),'action_type':'hotkey','arguments':{'keys':['meta','a']},'goal':'选中当前内容以完整替换'},
          {**common,'operation_id':f'field-{index}-type','action_type':'type','arguments':{'text':value},'goal':'将「'+label+'」填写为「'+value+'」'}])
    operations.append({'operation_id':'generate','subgoal_id':'result','action_type':'click','selector':'#generateBtn',
                       'evidence':{'target_label':'生成占位图'},'goal':'生成400×200、文字为「预览图」的占位图'})
    return operations

def inspect_placeholder_png(data_uri,expected_size=(400,200)):
    """Independent PNG decoding, dimensions and pixel digest; no text claim."""
    from PIL import Image
    if not isinstance(data_uri,str) or not data_uri.startswith('data:image/png;base64,') or len(data_uri)>2000000:raise ValueError('Expected bounded embedded PNG')
    raw=base64.b64decode(data_uri.split(',',1)[1],validate=True)
    with Image.open(BytesIO(raw)) as original:
        if original.format!='PNG' or original.size!=tuple(expected_size):raise ValueError('PNG dimensions differ from requested size')
        image=original.convert('RGBA')
        if image.getextrema()[3]!=(255,255):raise ValueError('Unexpected transparent placeholder pixels')
        rgb=image.convert('RGB');background=rgb.getpixel((0,0))
        points=[(x,y) for y in range(rgb.height) for x in range(rgb.width) if rgb.getpixel((x,y))!=background]
        if not points:raise ValueError('Blank PNG cannot prove requested text')
        bounds=[min(x for x,y in points),min(y for x,y in points),max(x for x,y in points)+1,max(y for x,y in points)+1]
        if background!=(238,238,238) or not (0<bounds[0]<bounds[2]<rgb.width and 0<bounds[1]<bounds[3]<rgb.height):raise ValueError('Expected centered gray-theme foreground')
        return {'width':rgb.width,'height':rgb.height,'background_rgb':list(background),'ink_bbox':bounds,
                'ink_pixels':len(points),'png_sha256':hashlib.sha256(raw).hexdigest(),'rgb_sha256':hashlib.sha256(rgb.tobytes()).hexdigest(),
                'text_semantics':'REQUIRES_INDEPENDENT_PIXEL_REVIEW_OR_OCR'}

def placeholder_spec(capability,page,widget,strategy_version):
    validate_observation(capability,page,widget)
    return {'page_uri':URI,'widget_adapter':ADAPTER_ID,'form_label':widget['label'],
      'goal':'在「在线占位图生成工具」中，将宽度改为400、高度改为200、自定义文本改为「预览图」，保持字体大小24、字体Arial和gray主题，点击「生成占位图」并核对完整预览图片。',
      'inputs':[{'selector':s,'label':l,'value':v} for s,l,v in EXPECTED_INPUTS],
      'deterministic_strategy':{'id':STRATEGY_ID,'version':strategy_version,'business_goal':'生成自定义尺寸与文字的占位图片',
       'operator':'original PNG dimension/pixel equality plus independent fixed-threshold OCR','expected_size':[400,200],
       'expected_text':'预览图','font_size':'24','font_family':'Arial','theme':'gray',
       'assurance':'Original screenshot ROI OCR without expected/custom words, minimum confidence 0.9; exact generated PNG/raster pixel equality'}}

def validate_placeholder_assertion_scope(task,condition):
    if (condition!={'selector':IMAGE_SELECTOR,'placeholder_png_text':'预览图'} or
        not all(matches_uri(task.get(k,'')) for k in ('initial_url','site_uri')) or
        task.get('deterministic_strategy',{}).get('id')!=STRATEGY_ID):
        raise ValueError('Placeholder pixel assertion requires exact URI, business and fixed Chinese text')

def compile_placeholder(capability,spec,task_version='observed-placeholder-compiler-1'):
    from .planning import object_sha256
    from .collect import validate_plan
    from .task_contract import validate_m4_task
    from .task_instruction import validate_task_instruction
    pages=[p for p in capability['capabilities'] if p['page_uri']==URI]
    if len(pages)!=1:raise ValueError('Placeholder must bind one observed page')
    page=pages[0];widgets=[w for w in page.get('widgets',[]) if w.get('adapter_id')==ADAPTER_ID]
    if len(widgets)!=1 or placeholder_spec(capability,page,widgets[0],spec['deterministic_strategy']['version'])!=spec:
        raise ValueError('Placeholder specification changed from observed controls')
    operations=development_operations();subgoals=[]
    for n,(selector,label,value) in enumerate(EXPECTED_INPUTS,1):
        for operation in operations[(n-1)*3:n*3]:
            operation.update(rationale='使用任务要求的新值完整替换当前输入',expected='输入框显示任务要求的值' if operation['action_type']=='type' else '输入内容已定位或选中')
        operations[n*3-1]['postconditions']=[{'selector':selector,'value':value}]
        subgoals.append({'id':f'field-{n}','description':'填写「'+label+'」','evidence':[{'operation_id':f'field-{n}-type','postcondition_index':0}]})
    assertions=[{'selector':IMAGE_SELECTOR,'placeholder_png_text':'预览图'}]+[
        {'selector':s,'value':v} for s,v in [('#width','400'),('#height','200'),('#customText','预览图'),
                                          ('#fontSize','24'),('#fontFamily','Arial'),('#theme','gray')]]
    operations[-1].update(rationale='用已填写的尺寸和文字更新图片预览',expected='完整显示400×200且含预览图文字的图片',postconditions=assertions)
    subgoals.append({'id':'result','description':'核对完整占位图','evidence':[{'final_assertion_index':0}]})
    task={'task_id':'placeholder-'+object_sha256({'capability':capability['capability_id'],'spec':spec})[:24],
      'task_version':task_version,'capability_id':capability['capability_id'],'capability_version':capability['version'],
      'task_family':'form-workflow','site_uri':capability['site_uri'],'site_category':capability['site_category'],
      'initial_url':URI,'app_name':page['title'],'instruction':spec['goal'],'task_type':['填写表单'],
      'stop_when_final':True,'content_preparation':False,'operations':operations,'subgoals':subgoals,
      'required_actions':[o['operation_id'] for o in operations],'final_assertions':assertions,
      'final_result':'完整显示400×200、文字为预览图的占位图片',
      'completion_judgement':'从原始末帧图像确认实际尺寸和预览图文字，不以输入框或alt替代图片结果。',
      'deterministic_strategy':spec['deterministic_strategy'],'capability_screen_status':capability['status'],
      'capability_review_required':capability['status']!='ready'}
    validate_task_instruction(task['instruction']);validate_plan({'tasks':[task]});validate_m4_task(task)
    return task
