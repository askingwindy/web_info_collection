"""Read-only adapter for the observed Lddgo ASCII-art widget.

A blank result only identifies a prospective output. This module does not grant
capability approval. An independently checked rendering oracle is required before
this widget can generate a production task.
"""
from urllib.parse import urlsplit

ADAPTER_ID = 'lddgo-ascii-art-widget-1'
STRATEGY_ID = 'text-to-ascii-art-v1'
URI = 'https://www.lddgo.net/string/text-to-ascii-art'


def matches_uri(uri):
    return urlsplit(uri) == urlsplit(URI)


ASCII_ART_INVENTORY_JS = r'''() => {
 const empty={widgets:[],result_targets:[],widget_rejections:[]};
 if(location.href!=='https://www.lddgo.net/string/text-to-ascii-art')return empty;
 const id='lddgo-ascii-art-widget-1',clean=s=>(s||'').replace(/\s+/g,' ').trim();
 const fail=reason=>({...empty,widget_rejections:[{adapter_id:id,page_uri:location.href,reason}]});
 const one=(s,r=document)=>r.querySelectorAll(s).length===1?r.querySelector(s):null;
 const visible=e=>{if(!e||!e.checkVisibility({checkOpacity:true,checkVisibilityCSS:true}))return false;
  const r=e.getBoundingClientRect(),h=document.elementFromPoint((r.left+r.right)/2,(r.top+r.bottom)/2);
  return r.width>0&&r.height>0&&r.left>=0&&r.top>=0&&r.right<=innerWidth&&r.bottom<=innerHeight&&!!h&&(h===e||e.contains(h));};
 const input=one('#inputContent'),width=one('#lineWidth'),button=one('#startGenerator'),result=one('#transformResult');
 if(!input||!width||!button||!result)return fail('Missing or ambiguous ASCII-art business controls');
 const root=input.closest('.layui-form.layui-form-pane');
 if(!root||!root.contains(width)||!root.contains(button)||!root.contains(result)||input.form||width.form||button.form)
  return fail('ASCII-art non-form grouping changed');
 const exactIds=['inputContent','lineWidth','startGenerator','startCopy','startDownload','startClear',
  'textFont','charWidth','charHeight','textFormat'];
 const controls=[...root.querySelectorAll('textarea,select,button,input:not([readonly]),[contenteditable=true]')];
 if(controls.length!==exactIds.length||controls.some(e=>!exactIds.includes(e.id)))return fail('ASCII-art controls changed');
 const fields=[];
 for(const [e,tag,type,label] of [[input,'textarea','textarea','文本内容'],[width,'input','number','行宽']]){
  const group=e.closest(e===input?'.layui-form-item':'.layui-inline');
  const observed=group&&one('.layui-form-label',group);
  if(e.localName!==tag||e.type!==type||e.disabled||e.readOnly||!visible(e)||!observed||!visible(observed)||clean(observed.innerText)!==label)
   return fail('ASCII-art field role or full viewport visibility changed; explicit scroll may be required');
  fields.push({selector:'#'+e.id,tag,type,label,visible:true,enabled:true,value:e.value,
   placeholder:e.placeholder||'',action_anchor:e.value||e.placeholder||'',
   label_source:'same_business_group_label',min:e.min||'',max:e.max||'',options:[]});
 }
 if(width.min!=='50'||width.max||button.localName!=='button'||!['submit','button'].includes(button.type)||
   button.disabled||!visible(button)||clean(button.innerText)!=='生成')return fail('ASCII-art width limit or generate control changed');
 fields.push({selector:'#startGenerator',tag:'button',type:button.type,label:'生成',visible:true,enabled:true,value:''});
 const settings=[];
 for(const [sid,label,value,display] of [['textFont','字体','Default','默认'],['charWidth','字符宽度','full','Full'],
    ['charHeight','字符高度','full','Full'],['textFormat','格式化','no','无']]){
  const select=one('#'+sid),group=select?.closest('.layui-inline'),caption=group&&one('.layui-form-label',group);
  const wrapper=select?.nextElementSibling,shown=wrapper&&one('input[readonly]',wrapper);
  if(!select||select.localName!=='select'||!root.contains(select)||select.disabled||select.value!==value||
     !caption||!visible(caption)||clean(caption.innerText)!==label||!wrapper?.classList.contains('layui-form-select')||
     !shown||!visible(shown)||shown.value!==display||select.selectedOptions.length!==1||clean(select.selectedOptions[0].textContent)!==display)
   return fail('ASCII-art default setting or its visible selected label changed');
  settings.push({selector:'#'+sid,label,value,display,visible:true,enabled:true});
 }
 const auxiliary=[];
 for(const [sid,label] of [['startCopy','复制'],['startDownload','下载'],['startClear','清空']]){
  const e=one('#'+sid);if(!e||!root.contains(e)||e.localName!=='button'||clean(e.innerText)!==label)
   return fail('ASCII-art auxiliary action grouping changed');
  auxiliary.push({selector:'#'+sid,label});
 }
 const resultGroup=result.closest('.layui-form-item'),resultLabel=resultGroup&&one('.layui-form-label',resultGroup);
 if(result.localName!=='pre'||!resultLabel||clean(resultLabel.textContent)!=='结果'||getComputedStyle(result).whiteSpace!=='pre')
  return fail('ASCII-art preformatted result role changed');
 const rr=result.getBoundingClientRect();
 return {widgets:[{kind:'non-form-widget',adapter_id:id,page_uri:location.href,label:'在线生成ASCII艺术字',fields,settings,auxiliary,
   observed_scroll_y:scrollY,viewport:[innerWidth,innerHeight],
   result_document_rect:[rr.left+scrollX,rr.top+scrollY,rr.right+scrollX,rr.bottom+scrollY],
   result_selector:'#transformResult',result_label:'结果'}],
  result_targets:[{selector:'#transformResult',text:clean(result.innerText),raw_text:result.textContent,visible:visible(result),
   label:'结果',business_label:'ASCII艺术字',preformatted:true}],widget_rejections:[]};
}'''


def validate_observation(capability, page, widget):
    """Return only a verified input intent; this is not a completion oracle."""
    if not all(matches_uri(u) for u in (capability['site_uri'], page['page_uri'], widget.get('page_uri',''))):
        raise ValueError('ASCII-art requires its exact observed URI')
    if (widget.get('kind'),widget.get('adapter_id'),widget.get('label')) != (
            'non-form-widget',ADAPTER_ID,'在线生成ASCII艺术字'):
        raise ValueError('ASCII-art widget identity changed')
    fields=widget['fields']
    if len(fields)!=3 or {f['selector'] for f in fields}!={'#inputContent','#lineWidth','#startGenerator'}:
        raise ValueError('ASCII-art needs its two input roles and generate control')
    observed={f['selector']:f for f in fields}; inputs=[]
    for selector,tag,kind,label,value in (('#inputContent','textarea','textarea','文本内容','HELLO'),
                                         ('#lineWidth','input','number','行宽','100')):
        f=observed[selector]
        if (f.get('tag'),f.get('type'),f.get('label'),f.get('visible'),f.get('enabled'),f.get('label_source')) != (
                tag,kind,label,True,True,'same_business_group_label'):
            raise ValueError('ASCII-art input role/visibility changed')
        if not isinstance(f.get('value'),str) or f['value']==value:
            raise ValueError('ASCII-art input state is missing or already requested')
        expected_initial,expected_placeholder,expected_anchor=(
            ('hello','','hello') if selector=='#inputContent' else ('','可选','可选'))
        if (f['value'],f.get('placeholder'),f.get('action_anchor'))!=(
                expected_initial,expected_placeholder,expected_anchor):
            raise ValueError('ASCII-art observed native value/placeholder action anchor changed')
        if selector=='#lineWidth' and (f.get('min'),f.get('max'))!=('50',''):
            raise ValueError('ASCII-art line-width constraint changed')
        inputs.append({'selector':selector,'label':label,'value':value})
    b=observed['#startGenerator']
    if (b.get('tag'),b.get('label'),b.get('visible'),b.get('enabled'))!=('button','生成',True,True) or b.get('type') not in ('submit','button'):
        raise ValueError('ASCII-art generate control changed')
    expected=[('#textFont','字体','Default','默认'),('#charWidth','字符宽度','full','Full'),
              ('#charHeight','字符高度','full','Full'),('#textFormat','格式化','no','无')]
    settings=widget.get('settings',[])
    if len(settings)!=len(expected) or [(s.get('selector'),s.get('label'),s.get('value'),s.get('display')) for s in settings]!=expected or any(
            s.get('visible') is not True or s.get('enabled') is not True for s in settings):
        raise ValueError('ASCII-art needs the four observed visible default settings')
    if widget.get('auxiliary')!=[{'selector':'#'+sid,'label':label} for sid,label in
            [('startCopy','复制'),('startDownload','下载'),('startClear','清空')]]:
        raise ValueError('ASCII-art auxiliary actions changed')
    if (widget.get('result_selector'),widget.get('result_label'))!=('#transformResult','结果'):
        raise ValueError('ASCII-art result role changed')
    results=[r for r in page['result_targets'] if r['selector']=='#transformResult']
    if len(results)!=1 or (results[0].get('label'),results[0].get('business_label'),results[0].get('preformatted'))!=('结果','ASCII艺术字',True):
        raise ValueError('ASCII-art preformatted result evidence missing')
    if results[0].get('raw_text','').strip() or results[0].get('text','').strip():
        raise ValueError('ASCII-art initial result must be observed empty for this bounded strategy')
    return inputs


def parse_ascii_figlet(font_text):
    """Parse only mandatory ASCII glyph rows; no kerning, smushing or wrapping.

    The recorded FIGlet source's format is independently implemented here. This
    deliberately refuses right-to-left fonts and incomplete/unequal glyph rows.
    """
    lines=font_text.replace('\r\n','\n').replace('\r','\n').split('\n')
    header=lines[0].split()
    if len(header)<6 or len(header[0])!=6 or not header[0].startswith('flf2a'):
        raise ValueError('Unsupported FIGlet header')
    height,comments=int(header[1]),int(header[5]);hardblank=header[0][5]
    if not 1<=height<=32 or comments<0 or (len(header)>6 and int(header[6])!=0):
        raise ValueError('Unsupported FIGlet height/comments/direction')
    offset=1+comments
    if len(lines)<offset+95*height:raise ValueError('Incomplete ASCII glyph table')
    glyphs={}
    for code in range(32,127):
        glyph=[]
        for row in lines[offset:offset+height]:
            if not row or row[-1].isspace():raise ValueError('Missing FIGlet end marker')
            glyph.append(row.rstrip(row[-1]).replace(hardblank,' '))
        if len({len(row) for row in glyph})!=1:raise ValueError('Unequal FIGlet glyph row widths')
        glyphs[chr(code)]=glyph;offset+=height
    return glyphs


def render_full_ascii(glyphs,text,max_width=100):
    """Concatenate fixed glyph rows; restrict to one ASCII input line fitting width."""
    if not isinstance(text,str) or not text or any(c not in glyphs for c in text):
        raise ValueError('Unsupported character in full-layout text')
    height=len(glyphs[text[0]])
    if not height or any(len(glyphs[c])!=height for c in text):raise ValueError('Inconsistent glyph heights')
    rows=[''.join(glyphs[c][row] for c in text) for row in range(height)]
    if not 1<=max_width<=1000 or max(map(len,rows))>max_width:
        raise ValueError('Wrapping is outside this fixed full-layout strategy')
    return '\n'.join(rows)


# Standard font by Glenn Chappell and Ian Chai; unmodified H/E/L/O glyph excerpts.
FONT_SHA256 = '44573a1b2145dfdf0110b6a2d3d98bdc47a98cca50795bd7b78278ee5ca96f79'
STANDARD_GLYPHS = {'H': ['  _   _ ', ' | | | |', ' | |_| |', ' |  _  |', ' |_| |_|', '        '], 'E': ['  _____ ', ' | ____|', ' |  _|  ', ' | |___ ', ' |_____|', '        '], 'L': ['  _     ', ' | |    ', ' | |    ', ' | |___ ', ' |_____|', '        '], 'O': ['   ___  ', '  / _ \\ ', ' | | | |', ' | |_| |', '  \\___/ ', '        ']}


def expected_hello():
    return render_full_ascii(STANDARD_GLYPHS,'HELLO',100)


def verify_ascii_result_text(raw_text):
    """Exact full glyph pattern, including line/space structure, for this task only."""
    return isinstance(raw_text,str) and raw_text.replace('\r\n','\n')==expected_hello()


def ascii_art_spec(capability,page,widget,strategy_version):
    import math
    inputs=validate_observation(capability,page,widget)
    if widget.get('viewport')!=[1280,720]:raise ValueError('ASCII-art geometry requires the production viewport')
    initial=widget.get('observed_scroll_y');rect=widget.get('result_document_rect')
    if type(initial) not in (int,float) or not math.isfinite(initial) or initial!=int(initial) or not 0<initial<=600:
        raise ValueError('ASCII-art needs a recorded necessary initial scroll and visible controls')
    if not isinstance(rect,list) or len(rect)!=4 or any(type(n) not in (int,float) or not math.isfinite(n) for n in rect):
        raise ValueError('ASCII-art result document geometry is missing')
    left,top,right,bottom=rect
    if not (0<=left<right<=1280 and 0<bottom-top<=600):raise ValueError('ASCII-art result cannot fit the viewport')
    final=math.ceil(bottom-650)
    if not initial<final<=1200:raise ValueError('ASCII-art result view needs a separately supported scroll strategy')
    normalized=' '.join(expected_hello().split())
    return {'page_uri':URI,'form_label':widget['label'],'widget_adapter':ADAPTER_ID,
      'goal':'在「在线生成ASCII艺术字」中使用默认字体、Full字符宽度与高度及无格式化，将文本内容填写为HELLO、行宽填写为100，点击「生成」，查看完整的HELLO艺术字结果。',
      'inputs':inputs,'submit':{'selector':'#startGenerator','label':'生成'},
      'completion':{'selector':'#transformResult','contains':normalized,'description':'默认字体的HELLO艺术字完整显示'},
      'initial_scroll_y':int(initial),'result_scroll_y':final,
      'deterministic_strategy':{'id':STRATEGY_ID,'version':strategy_version,'business_goal':'文本生成ASCII艺术字',
       'operator':'full-layout ASCII glyph row concatenation','font_sha256':FONT_SHA256,'input_text':'HELLO','line_width':100,
       'observed_roles':['文本内容','行宽'],'expected_raw':expected_hello(),
       'assurance':'Independent Python full-layout rendering from source-linked Standard font glyphs; fixed HELLO/100/default/full/full/no only; original-frame review still required'}}


def compile_ascii_art(capability,spec,task_version='observed-ascii-art-compiler-1'):
    """Compile exact observed controls with two necessary view-changing scrolls."""
    from .planning import object_sha256
    from .collect import validate_plan
    from .task_contract import validate_m4_task
    from .task_instruction import validate_task_instruction
    pages=[p for p in capability['capabilities'] if p['page_uri']==spec['page_uri']]
    if len(pages)!=1:raise ValueError('ASCII-art must bind one observed page')
    page=pages[0];widgets=[w for w in page.get('widgets',[]) if w.get('adapter_id')==ADAPTER_ID]
    if len(widgets)!=1:raise ValueError('ASCII-art must bind one observed widget')
    if ascii_art_spec(capability,page,widgets[0],spec['deterministic_strategy']['version'])!=spec:
        raise ValueError('ASCII-art specification changed from observed strategy')
    widget=widgets[0];fields={f['selector']:f for f in widget['fields']};ops=[];subgoals=[]
    ops.append({'operation_id':'view-inputs','subgoal_id':'field-1','action_type':'scroll',
      'arguments':{'direction':'down'},'execution':{'distance':spec['initial_scroll_y']},
      'goal':'向下滚动以完整显示文本、行宽和生成控件','rationale':'初始视口下方的行宽和生成控件需要显式滚动进入视口',
      'expected':'文本内容、行宽和生成控件完整显示'})
    for n,request in enumerate(spec['inputs'],1):
        sid='field-'+str(n);selector=request['selector'];label=request['label'];value=request['value']
        # The textarea label is above it and lineWidth uses an inline group.
        # Existing snapshot support does not infer these labels. Bind actions
        # to the actual readable native value/placeholder instead; keep the
        # independently checked business role in the task and subgoal prose.
        common={'subgoal_id':sid,'selector':selector,
                'evidence':{'target_label':fields[selector]['action_anchor']}}
        ops.append({**common,'operation_id':sid+'-focus','action_type':'click','goal':'选中「'+label+'」',
          'rationale':'填写该项前先聚焦输入位置','expected':'光标进入「'+label+'」'})
        if fields[selector]['value']:
            ops.append({'operation_id':sid+'-select','subgoal_id':sid,'action_type':'hotkey','arguments':{'keys':['meta','a']},
              'goal':'选中当前输入内容','rationale':'原输入已有内容，需要整体替换','expected':'当前内容被选中'})
        ops.append({**common,'operation_id':sid+'-type','action_type':'type','arguments':{'text':value},
          'goal':'将「'+label+'」填写为「'+value+'」','rationale':'设置任务要求的必要输入','expected':'输入框显示「'+value+'」',
          'postconditions':[{'selector':selector,'value':value}]})
        subgoals.append({'id':sid,'description':'填写「'+label+'」','evidence':[{'operation_id':sid+'-type','postcondition_index':0}]})
    ops.append({'operation_id':'generate','subgoal_id':'result','action_type':'click','selector':'#startGenerator',
      'evidence':{'target_label':'生成'},'goal':'点击「生成」','rationale':'根据文本和行宽生成ASCII艺术字','expected':'艺术字结果区域更新'})
    assertions=[{'selector':'#transformResult','contains':spec['completion']['contains']},
                {'selector':'#lineWidth','value':'100'}]
    ops.append({'operation_id':'view-result','subgoal_id':'result','action_type':'scroll','arguments':{'direction':'down'},
      'execution':{'distance':spec['result_scroll_y']-spec['initial_scroll_y']},'goal':'向下滚动查看完整艺术字结果',
      'rationale':'结果框在当前视口下方，须完整呈现后核验字形','expected':spec['completion']['description'],
      'postconditions':assertions})
    subgoals.append({'id':'result','description':'核对完整HELLO艺术字','evidence':[{'final_assertion_index':0}]})
    task={'task_id':'ascii-art-'+object_sha256({'capability':capability['capability_id'],'spec':spec})[:24],
      'task_version':task_version,'capability_id':capability['capability_id'],'capability_version':capability['version'],
      'task_family':'form-workflow','site_uri':capability['site_uri'],'site_category':capability['site_category'],
      'initial_url':URI,'app_name':page['title'],'instruction':spec['goal'],'task_type':['填写表单'],
      'stop_when_final':True,'content_preparation':False,'operations':ops,'subgoals':subgoals,
      'required_actions':[o['operation_id'] for o in ops],'final_assertions':assertions,
      'final_result':spec['completion']['description'],'completion_judgement':'核对最终原图中完整显示HELLO艺术字，行宽为100。',
      'deterministic_strategy':spec['deterministic_strategy'],'capability_screen_status':capability['status'],
      'capability_review_required':capability['status']!='ready'}
    validate_task_instruction(task['instruction']);validate_plan({'tasks':[task]});validate_m4_task(task)
    return task
