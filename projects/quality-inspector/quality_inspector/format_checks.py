"""Sample-derived CUSTOMER PROXY precheck, NOT the customer's executable.

Uses archived customer prose as authority; never imports internal M1 constants.
Read-only on inputs. Report paths must be outside input samples.
"""
import argparse,csv,hashlib,json,re,sys
from collections import Counter,defaultdict
from datetime import datetime
from pathlib import Path
from urllib.parse import urlsplit
from PIL import Image
from .checksums import verify_manifest
from .layout import discover, package_document_paths
from jsonschema import Draft202012Validator,validators

VERSION='customer-proxy-0.2'
REQ='request/web操作采集需求/需求书-Web浏览器自动化操作轨迹数据集.md'
A='request/web操作采集需求/附件A-字段说明.md'
B='request/web操作采集需求/附件B-动作空间与坐标系.md'
CL='request/需求澄清记录.md'
EX='request/web操作采集需求/samples/样例说明.md'
LABELS=['搜索查询','填写表单','修改设置','创建/编辑/保存文件','发送消息','预约日程','购买流程','筛选排序','上传下载','导入导出','权限配置','内容发布','数据查看','问题排查']
ACTIONS={'click':{'x':'integer','y':'integer'},'double_click':{'x':'integer','y':'integer'},'right_click':{'x':'integer','y':'integer'},'type':{'text':'string'},'hotkey':{'keys':'strings'},'scroll':{'x':'integer','y':'integer','direction':'direction'},'drag':{'x':'integer','y':'integer','end_x':'integer','end_y':'integer'},'back':{},'open_url':{'url':'string'},'select':{'x':'integer','y':'integer','option':'string'},'wait':{},'complete':{'status':'complete_status'}}
CONTROL={'click','double_click','right_click','type','drag','select'}
POINTER={'click','double_click','right_click','scroll','drag','select'}
CSV_FIELDS=['sample_id','site_id','site_category','app_name','task_type','task_instruction','steps','screen_resolution','completion_status','actions','bytes']
CATALOG=[
 ('C01','confirmed','required fields and JSON types',A+'#顶层字段 / 步骤字段 / 动作字段',REQ+'#7.1'),
 ('C02','confirmed','documented terminal/language/risk/completion/state enums',A+'#字段表'),
 ('C03','confirmed','task_type 1–3 values in 14 documented categories',REQ+'#4',EX+'#两处别照抄'),
 ('C04','confirmed','truthful source enum; data_type/action_space strings, no guessed constant',A+'#trajectory_source',EX+'#两处别照抄'),
 ('C05','confirmed','step numbering, sample file layout, no extra sample files',REQ+'#3 / #7.2–5',EX+'#每条的结构'),
 ('C06','confirmed','PNG files, identical resolution, image/tree linkage',REQ+'#7.3–4',A+'#界面树文件 / 通用约定'),
 ('C07','confirmed','unique element IDs and resolvable action/parent references; exact target text',A+'#界面树文件',REQ+'#7.8'),
 ('C08','confirmed','integer pixel coordinates, valid boxes, point/arguments consistency',B+'#1–2',REQ+'#4 / #7.7'),
 ('C09','confirmed','Web action/tool equality, documented arguments and canonical Windows shortcut delivery representation',B+'#1',CL+'#快捷键的 Windows 交付表达',REQ+'#7.9'),
 ('C10','confirmed','success states and explicit final complete',REQ+'#6 / #7.10–11',A+'#final_state_image'),
 ('C11','confirmed','five effective steps excluding wait/complete, or short-flow reason',CL+'#有效操作步',REQ+'#2 / #7.6'),
 ('C12','confirmed','text has no prohibited process/selector fragments; task titles use corner quotes; step_result excludes observation placeholders and known navigation noise',REQ+'#7.14–15',REQ+'#6.任务指令专有名词',A+'#步骤字段/step_result'),
 ('C13','confirmed','batch metadata rows, qc_report and SHA256SUMS',REQ+'#3 / #7'),
 ('C14','confirmed','source/collection/readme/ground-truth documentation supplied outside samples',REQ+'#3'),
 ('C15','confirmed','IDs unique within inspected package',REQ+'#3',A+'#sample_id'),
 ('C17','confirmed','any exact screenshot shared by different trajectories is a duplicate hit',REQ+'#6.截图完全相同'),
 ('C16','confirmed','timestamps ISO8601 if available; empty is allowed',A+'#tool_call'),
 ('I01','inferred','exact sample_id regex, directory-name equality, site digit count',EX+'#两条样例',REQ+'#3'),
 ('I02','inferred','unknown additional fields and CSV array encoding acceptance',EX+'#样例',A+'#字段表'),
 ('I03','inferred','action_space unified_gui_v4 appears in both samples; not a closed enum',B+'#动作空间',EX+'#样例'),
 ('U01','unknown','actual customer executable, version, machine schema and errors unavailable',REQ+'#7.我方验收方式'),
 ('U02','documentary','supplied lineage mapping; external registration is not required by archived prose',A+'#trajectory_source',EX+'#两处别照抄'),
 ('U03','unknown','Chinese technical terms/control labels and language acceptance',REQ+'#5',A+'#通用约定'),
 ('U04','unknown','pixel semantic continuity, real viewport/truth/privacy and final result acceptance',REQ+'#1 / #4 / #7.13,16,17',CL+'#账号与页面信息'),
 ('U05','unknown','complete delivery distributions, four-route near-duplicate adjudication and customer sampling',REQ+'#2 / #5–7'),
 ('N01','confirmed','no later website replay required; archived user clarification overrides replay clause',CL+'#验收范围')]

def _task_titles_outside_corner_quotes(text):
    """Literal task-only check; preserve book marks inside quoted original text.

    Customer references use book marks in ordinary step prose, so this check
    does not reinterpret those fields or synchronized target/control strings.
    It is implemented here independently of any producer text transformer.
    """
    depth=0;books=[];outside=[]
    for index,character in enumerate(text):
        if character=='「':depth+=1
        elif character=='」':depth=max(0,depth-1)
        elif character=='《':books.append((index,depth))
        elif character=='》' and books:
            start,opening_depth=books.pop()
            if opening_depth==0:outside.append(text[start:index+1])
    return outside


def prohibited_narrative(text):
    """Literal contract exclusions only; this is not full language validation.

    Quoted original UI names can contain hashes or technical identifiers. New
    selector/identifier heuristics inspect unquoted prose and explicit machine
    labels, rather than rejecting every occurrence of an English word.
    """
    reasons=[]
    if re.search(r'DOM|XPath|红圈|蓝框|触点|按既定流程|回放|脚本|%[0-9a-fA-F]{2}',text):
        reasons.append('prohibited process/selector text')
    depth=0;unquoted=[]
    for character in text:
        if character=='「':depth+=1;unquoted.append(' ')
        elif character=='」':depth=max(0,depth-1);unquoted.append(' ')
        elif not depth:unquoted.append(character)
    visible_prose=''.join(unquoted)
    patterns=[
        (r'(?<![\w#])#[A-Za-z_][\w-]*','unquoted CSS ID selector'),
        (r'(?:CSS\s*)?(?:选择器|selector)\s*[:：=]?\s*[.#\[]','explicit selector label'),
        (r'(?<!\w)(?:e\d+|(?:node|element)[_:-]?\d+)(?!\w)','machine element identifier'),
        (r'(?:元素|控件)\s*(?:编号|[Ii][Dd])\s*[:：=]?\s*[A-Za-z0-9_-]+','machine element ID description'),
        (r'控件\s*\d+\s*个','DOM/control count description'),
    ]
    for pattern,reason in patterns:
        if re.search(pattern,visible_prose):reasons.append(reason)
    return reasons


def step_observation_issues(text):
    """Reject explicit non-observations, not infer full pixel semantics.

    This field must describe what changed. Deferring that description to a later
    reviewer or only reporting that an operation ran does not supply one. Exact
    quoted UI states remain possible observations and are left to visual review.
    The repeated numeral rule is intentionally limited to generated scroll prose;
    it does not ban ordinary numeric content, control labels or quoted source text.
    """
    reasons = []
    quoted_values = re.findall(r'「([^「」]*)」', text)
    unquoted = re.sub(r'「[^「」]*」', '', text)
    compact = re.sub(r'[\s，。；：、,.;:!?！？“”\"\'…]+', '', unquoted)
    if '具体可见变化待独立审核' in compact:
        reasons.append('step_result defers actual visible observations to a later review')
    elif not any(value.strip() for value in quoted_values):
        generic_clauses = [
            r'(?:已|已经)?(?:成功)?(?:执行|完成)(?:了)?(?:本步|当前|该)?(?:动作|操作|步骤)',
            r'(?:本步|当前|该)?(?:动作|操作|步骤)(?:已|已经)?(?:执行|完成|成功|结束)',
            r'(?:已|已经)?(?:点击|输入|滚动|返回)(?:成功|完成|结束)',
            r'(?:已|已经)?(?:保存|记录)(?:了)?(?:本步|后续|当前|实际|页面|界面|视口|截图|状态|证据|结果|操作后|动作后|的)+',
            r'(?:具体|实际|可见|详细)?(?:变化|结果|观察|内容|事实)(?:待|等待|留待)(?:独立|人工)?(?:审核|复核|核实|核验|核对)',
            r'(?:待|等待|留待)(?:独立|人工)?(?:审核|复核|核实|核验|核对)(?:具体|实际|可见|详细)?(?:变化|结果|观察|内容|事实)',
            r'(?:待|等待|留待)(?:独立|人工)?(?:审核|复核|核实|核验|核对)',
            r'(?:页面|界面)(?:已|已经)?(?:发生变化|更新|改变)',
            r'(?:可|将)?(?:继续|进入)(?:下一步|后续步骤)',
        ]
        clauses = [re.sub(r'\s+', '', part) for part in re.split(r'[，。；,;.!！?？]+|并且|并', unquoted) if part.strip()]
        if clauses and all(any(re.fullmatch(pattern, part) for pattern in generic_clauses) for part in clauses):
            reasons.append('step_result only reports generic execution or deferred review without an actual observation')
    if re.search(r'滚动.*可见(?:文字|正文)', text):
        for quoted in re.findall(r'「([^「」]*)」', text):
            tokens = re.findall(r'[\u4e00-\u9fffA-Za-z0-9]+', quoted)
            if (len(tokens) >= 4 and len(set(tokens)) == 1
                    and re.fullmatch(r'[一二三四五六七八九十]', tokens[0])):
                reasons.append('step_result quotes repeated navigation numerals instead of a meaningful visible change')
                break
    return reasons


_WINDOWS_MODIFIERS = ('ctrl', 'alt', 'shift', 'win')
_WINDOWS_ALIASES = {'control': 'ctrl', 'ctl': 'ctrl', 'windows': 'win', 'super': 'win',
                    'return': 'enter', 'esc': 'escape', 'spacebar': 'space',
                    'pgup': 'pageup', 'pgdn': 'pagedown', 'del': 'delete', 'ins': 'insert',
                    'left': 'arrowleft', 'right': 'arrowright', 'up': 'arrowup', 'down': 'arrowdown'}
_WINDOWS_NAMES = {'enter', 'escape', 'tab', 'backspace', 'delete', 'insert', 'space',
                  'home', 'end', 'pageup', 'pagedown', 'arrowleft', 'arrowright',
                  'arrowup', 'arrowdown', 'capslock', 'numlock', 'scrolllock', 'pause',
                  'printscreen', 'contextmenu'}
_WINDOWS_LABELS = {'ctrl': 'Ctrl', 'alt': 'Alt', 'shift': 'Shift', 'win': 'Win',
                   'enter': 'Enter', 'escape': 'Esc', 'tab': 'Tab', 'backspace': 'Backspace',
                   'delete': 'Delete', 'insert': 'Insert', 'space': 'Space', 'home': 'Home',
                   'end': 'End', 'pageup': 'PageUp', 'pagedown': 'PageDown', 'arrowleft': 'Left',
                   'arrowright': 'Right', 'arrowup': 'Up', 'arrowdown': 'Down',
                   'capslock': 'CapsLock', 'numlock': 'NumLock', 'scrolllock': 'ScrollLock',
                   'pause': 'Pause', 'printscreen': 'PrintScreen', 'contextmenu': 'ContextMenu'}
_MAC_COMMAND_KEYS = set('acvxzs fponwtlrdgbiuk'.replace(' ', ''))


def canonical_windows_keys(keys, source_os=None):
    """Independently normalize declared Windows delivery names, never raw logs.

    Only documented common Command chords have a functional Ctrl mapping.
    Ambiguous macOS shortcuts and unknown key names must be resolved explicitly.
    """
    def reject():
        raise ValueError('WINDOWS_SHORTCUT_MAPPING_REQUIRED')
    if (not isinstance(keys, list) or not keys or
            any(not isinstance(key, str) or not key or key != key.strip() for key in keys)):
        reject()
    os_name = source_os.casefold() if isinstance(source_os, str) else ''
    is_mac = os_name in {'mac', 'macos', 'darwin', 'mac os x'}
    is_windows = os_name in {'win32', 'win64'} or os_name.startswith('windows')
    modifiers = []; primary = None; command = False
    for key in keys:
        name = key.casefold()
        if name in {'option', 'opt', '⌥'}:
            reject()
        if name in {'meta', 'command', 'cmd', '⌘'}:
            if is_mac:
                name = 'command'
            elif is_windows and name == 'meta':
                name = 'win'
            else:
                reject()
        else:
            name = _WINDOWS_ALIASES.get(name, name)
        if name in _WINDOWS_MODIFIERS or name == 'command':
            if primary is not None or name in modifiers:
                reject()
            modifiers.append(name)
            command = command or name == 'command'
        else:
            if primary is not None:
                reject()
            if len(key) == 1 and key.isprintable():
                primary = key
            elif name in _WINDOWS_NAMES or re.fullmatch(r'f(?:[1-9]|1[0-9]|2[0-4])', name):
                primary = name
            else:
                reject()
    if primary is None:
        if len(modifiers) != 1 or command:
            reject()
        return modifiers
    if command:
        if ('alt' in modifiers or 'win' in modifiers or 'ctrl' in modifiers or
                not (primary.casefold() in _MAC_COMMAND_KEYS or
                     (primary in '123456789' and 'shift' not in modifiers))):
            reject()
        modifiers[modifiers.index('command')] = 'ctrl'
    if len(set(modifiers)) != len(modifiers):
        reject()
    if modifiers and len(primary) == 1:
        primary = primary.lower()
    return [name for name in _WINDOWS_MODIFIERS if name in modifiers] + [primary]


def windows_key_label(keys):
    return '+'.join(_WINDOWS_LABELS.get(key, key.upper() if len(key) == 1 or key.startswith('f') else key)
                    for key in keys)


def is_select_all_combination(keys):
    # Compatibility query only; every hotkey is now checked under one vocabulary.
    try:
        return canonical_windows_keys(keys, 'macOS') == ['ctrl', 'a']
    except ValueError:
        return False


def delivered_call_matches_capture(executed, delivered, source_os=None):
    """Preserve exact calls except the declared Windows shortcut mapping."""
    if executed == delivered:
        return True
    if not isinstance(executed, dict) or executed.get('tool_name') != 'hotkey':
        return False
    arguments = executed.get('arguments')
    if not isinstance(arguments, dict):
        return False
    try:
        keys = canonical_windows_keys(arguments.get('keys'), source_os)
    except ValueError:
        return False
    normalized = dict(executed, arguments=dict(arguments, keys=keys))
    return normalized == delivered


def catalog():
    rows=[{'id':r[0],'certainty':r[1],'rule':r[2],'sources':list(r[3:])} for r in CATALOG]
    provenance={
        'C03':{'authority':'customer-original-archive','locations':[REQ+':71 (ZIP original:69)',EX+':21'],
               'original_archive':'request/web操作采集需求.zip','production':'1–3 documented enum values',
               'reference_exception':'Empty task_type explicitly documented; field is present, not missing.'},
        'C04':{'authority':'customer-original-archive','locations':[A+':16',EX+':22'],
               'source_enum':['human','agent','human_agent_hybrid'],'no_forced_data_type':'T6 and internal webcollect_agent_v1 are not universal constants'},
        'I01':{'authority':'inferred; exact internal regex is not a customer requirement','locations':[REQ+':38–49'],
               'internal_only':'projects/code/webcollect/schemas/annotation.schema.json:6'}}
    for row in rows:
        if row['id'] in provenance:row['provenance']=provenance[row['id']]
    return rows
def obj(properties,required=None):return {'type':'object','properties':properties,'required':list(properties) if required is None else required,'additionalProperties':True}
def array(item,minimum=0,maximum=None):
    d={'type':'array','items':item,'minItems':minimum}
    if maximum is not None:d['maxItems']=maximum
    return d
S={'type':'string'};BOOL={'type':'boolean'};INT={'type':'integer'};NONEMPTY={'type':'string','minLength':1,'pattern':r'\S'}
RES=array({'type':'integer','minimum':1},2,2);BOX=array(INT,4,4)
ACTION=obj({'action_type':{'type':'string','enum':list(ACTIONS)},'target_element_id':S,'target_text':S,'coordinate':{'oneOf':[array(INT,0,0),array(INT,2,2)]},'input_text':S,'precondition':NONEMPTY,'expected_result':NONEMPTY,'target_bbox':BOX,'target_control_type':S,'end_coordinate':array(INT,2,2)},['action_type','target_element_id','target_text','coordinate','input_text','precondition','expected_result'])
TOOL=obj({'tool_name':S,'call_id':S,'arguments':{'type':'object'},'timestamp':S,'context':S})
STEP=obj({'step_id':INT,'image_path':NONEMPTY,'ui_tree_path':NONEMPTY,'page_name':NONEMPTY,'user_goal':NONEMPTY,'action':ACTION,'tool_call':TOOL,'tool_result':obj({'status':{'enum':['success','error']},'return_value':{'type':'object','properties':{'screen_changed':BOOL}},'error':S}),'next_step_rationale':NONEMPTY,'step_result':NONEMPTY,'exception_evidence':array(S)})
ANNOTATION=obj({'sample_id':NONEMPTY,'task_instruction':NONEMPTY,'task_type':array({'type':'string','enum':LABELS},1,3),'terminal_type':{'enum':['Android','iOS','Windows','macOS','Linux','Web']},'device_info':obj({'device_model':S,'os_name':S,'os_version':S,'screen_resolution':RES}),'app_info':obj({'app_name':NONEMPTY,'app_version':S,'environment':NONEMPTY,'ui_language':{'enum':['zh','en']}}),'risk_level':{'enum':['normal','sensitive','high_risk']},'trajectory_source':obj({'source_type':{'enum':['human','agent','human_agent_hybrid']},'data_type':NONEMPTY,'action_space':NONEMPTY}),'steps':array(STEP,1),'final_state_image':S,'final_result':NONEMPTY,'completion_status':{'enum':['success','controlled_exception','failed']},'completion_judgement':NONEMPTY,'short_flow':BOOL,'short_flow_reason':S},['sample_id','task_instruction','task_type','terminal_type','device_info','app_info','risk_level','trajectory_source','steps','final_result','completion_status','completion_judgement'])
ELEMENT=obj({'element_id':NONEMPTY,'parent_id':NONEMPTY,'element_type':NONEMPTY,'native_role':S,'text':S,'bbox':BOX,'clickable':BOOL,'inputable':BOOL,'scrollable':BOOL,'visible':BOOL,'enabled':BOOL,'state':{'enum':['default','selected','checked','unchecked','expanded','collapsed','disabled','focused']}})
STEP['properties']['tool_result']['properties']['return_value']['properties']['collection_ending']={
    'type':'object','properties':{'protocol':{'enum':['webcollect-five-eight-attempt-ending-2','webcollect-banded-attempt-ending-3','webcollect-continuous-attempt-ending-4']}},'required':['protocol']}
TREE=obj({'image_path':NONEMPTY,'screen_resolution':RES,'elements':array(ELEMENT)})
Strict=validators.extend(Draft202012Validator,type_checker=Draft202012Validator.TYPE_CHECKER.redefine('integer',lambda checker,value:type(value) is int))

def load(p):return json.loads(Path(p).read_text(encoding='utf-8'),parse_constant=lambda x:(_ for _ in ()).throw(ValueError('nonfinite JSON '+x)))
def sha(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()
def problem(rule,path,message,**extra):return {'rule_id':rule,'path':str(path),'message':message,**extra}
def safe_path(root,rel):
    p=root/rel
    if Path(rel).is_absolute() or not p.resolve().is_relative_to(root.resolve()):raise ValueError('reference escapes input sample')
    return p

def schema_errors(data,schema,prefix,rule='C01'):
    out=[]
    for e in sorted(Strict(schema).iter_errors(data),key=lambda e: str(list(e.absolute_path))):
        path=prefix+'/'+ '/'.join(map(str,e.absolute_path));actual_rule='C03' if '/task_type' in path else 'C04' if '/trajectory_source/' in path and e.validator=='enum' else 'C02' if e.validator=='enum' else rule
        out.append(problem(actual_rule,path,e.message))
    return out

def extra_fields(data,schema,path):
    out=[]
    if isinstance(data,dict) and schema.get('type')=='object' and 'properties' in schema:
        for key,value in data.items():
            if key not in schema['properties']:out.append(problem('I02',path+'/'+key,'Extra field not explicitly specified; customer acceptance UNKNOWN, not rejected by guessed additionalProperties=false.'))
            else:out.extend(extra_fields(value,schema['properties'][key],path+'/'+key))
    elif isinstance(data,list) and schema.get('type')=='array':
        for i,value in enumerate(data):out.extend(extra_fields(value,schema['items'],path+'/'+str(i)))
    return out

def sample_check(directory,diagnostic_allow_empty_task_type=False):
    directory=Path(directory).resolve();errors=[];observations=[];images=[]
    try:a=load(directory/'annotation.json')
    except (OSError,ValueError,UnicodeError) as e:return {'sample_path':str(directory),'confirmed_format_pass':False,'errors':[problem('C01','annotation.json',str(e))],'observations':[],'unknown_rule_ids':['U01','U02','U03','U04'],'customer_acceptance':'UNKNOWN','images':[]}
    schema=ANNOTATION
    if diagnostic_allow_empty_task_type:
        schema=json.loads(json.dumps(ANNOTATION));schema['properties']['task_type']['minItems']=0
    errors+=schema_errors(a,schema,'annotation')
    if errors:return {'sample_path':str(directory),'sample_id':a.get('sample_id') if isinstance(a,dict) else None,'confirmed_format_pass':False,'errors':errors,'observations':[],'unknown_rule_ids':['U01','U02','U03','U04'],'customer_acceptance':'UNKNOWN','images':[],'deep_checks':'not_run_due_to_schema_errors'}
    observations+=extra_fields(a,ANNOTATION,'annotation');res=a['device_info']['screen_resolution'];expected={'annotation.json'};call_ids=set();n=len(a['steps'])
    if directory.name!=a['sample_id']:observations.append(problem('I01','sample_id','Directory/internal sample_id differ. Required exact naming relationship is not specified unambiguously by customer prose; original examples themselves differ.'))
    if a['trajectory_source']['action_space']!='unified_gui_v4':observations.append(problem('I03','trajectory_source/action_space','Different from two example values; exact identifier acceptance remains UNKNOWN.'))
    if a['completion_status']=='failed':errors.append(problem('C10','completion_status','Failed trajectories cannot be delivered.'))
    effective=sum(st['action']['action_type'] not in ('wait','complete') for st in a['steps'])
    from webcollect.closing_policy import annotation_errors
    errors += [problem('C10','collection_ending',message) for message in annotation_errors(a)]
    if effective<5 and not(a.get('short_flow') is True and a.get('short_flow_reason','').strip()):errors.append(problem('C11','steps','Fewer than five effective actions without explicit short-flow reason.'))
    if a['app_info']['ui_language']!='zh':errors.append(problem('C02','app_info/ui_language','Web collection contract requires Chinese UI.'))
    def boxok(b):return 0<=b[0]<b[2]<=res[0] and 0<=b[1]<b[3]<=res[1]
    def pointok(p):return len(p)==2 and 0<=p[0]<res[0] and 0<=p[1]<res[1]
    for i,st in enumerate(a['steps'],1):
        label=f'steps/{i}';ac=st['action'];tool=st['tool_call'];t=ac['action_type'];args=tool['arguments'];tree=None;elements={}
        if st['step_id']!=i:errors.append(problem('C05',label+'/step_id','Step IDs must start at 1 and be consecutive.'))
        for kind,canonical in [('image_path',f'images/step_{i:03}.png'),('ui_tree_path',f'ui_tree/step_{i:03}.json')]:
            rel=st[kind];expected.add(rel)
            if rel!=canonical:errors.append(problem('C05',label+'/'+kind,'Expected '+canonical))
            try:
                p=safe_path(directory,rel)
                if p.is_symlink() or not p.is_file():raise FileNotFoundError('Missing or symlink evidence: '+rel)
                if kind=='image_path':
                    with Image.open(p) as im:
                        if im.format!='PNG' or list(im.size)!=res:errors.append(problem('C06',label+'/'+kind,'PNG format/resolution mismatch.'))
                        im.verify()
                    with Image.open(p) as im:im.load()
                    images.append({'step':i,'sha256':sha(p)})
                else:
                    tree=load(p);tree_errors=schema_errors(tree,TREE,label+'/tree');errors+=tree_errors
                    if tree_errors:tree=None
            except (OSError,ValueError,SyntaxError) as e:errors.append(problem('C06',label+'/'+kind,str(e)))
        if tree:
            if tree['image_path']!=st['image_path'] or tree['screen_resolution']!=res:errors.append(problem('C06',label+'/tree','Tree image link/resolution differs from synchronized screenshot.'))
            observations+=extra_fields(tree,TREE,label+'/tree')
            for e in tree['elements']:
                if e['element_id'] in elements or e['element_id']=='root':errors.append(problem('C07',label+'/tree/'+e['element_id'],'Duplicate/reserved element ID.'))
                elements[e['element_id']]=e
                if not boxok(e['bbox']):errors.append(problem('C08',label+'/tree/'+e['element_id'],'Invalid or out-of-viewport element box.'))
                if not e['visible']:errors.append(problem('C06',label+'/tree/'+e['element_id'],'Contract only includes visible elements.'))
            for eid,e in elements.items():
                parent=e['parent_id'];seen={eid}
                while parent!='root':
                    if parent not in elements or parent in seen:errors.append(problem('C07',label+'/tree/'+eid,'Unresolved/cyclic parent reference.'));break
                    seen.add(parent);parent=elements[parent]['parent_id']
        if tool['tool_name']!=t:errors.append(problem('C09',label+'/tool_call/tool_name','Tool name differs from action.'))
        if tool['call_id'] in call_ids:observations.append(problem('I02',label+'/tool_call/call_id','Repeated call_id; unique ID scope not explicitly given.'))
        call_ids.add(tool['call_id'])
        spec=ACTIONS[t]
        if set(args)!=set(spec):errors.append(problem('C09',label+'/tool_call/arguments','Keys must match documented action parameters: '+','.join(spec)))
        for k,typ in spec.items():
            if k not in args:continue
            v=args[k];valid=type(v)is int if typ=='integer' else isinstance(v,str) if typ=='string' else isinstance(v,list) and bool(v) and all(isinstance(x,str) and bool(x.strip()) for x in v) if typ=='strings' else v in ['up','down','left','right'] if typ=='direction' else v in ['success','infeasible']
            if not valid:errors.append(problem('C09',label+'/tool_call/arguments/'+k,'Invalid parameter type/value.'))
        if t=='open_url' and isinstance(args.get('url'),str):
            try:
                url=args['url'];parsed=urlsplit(url)
                valid=bool(url and parsed.scheme and (parsed.netloc or parsed.path)) and not any(c.isspace() for c in url)
                if parsed.scheme in ('http','https'):valid=valid and bool(parsed.hostname)
            except ValueError:valid=False
            if not valid:errors.append(problem('C09',label+'/tool_call/arguments/url','open_url requires an absolute, nonempty URL; no scheme or domain whitelist is imposed.'))
        if tool['timestamp']:
            try:datetime.fromisoformat(tool['timestamp'].replace('Z','+00:00'))
            except ValueError:errors.append(problem('C16',label+'/tool_call/timestamp','Not ISO8601.'))
        coordinate=ac['coordinate'];bbox=ac.get('target_bbox')
        if t in POINTER:
            if not pointok(coordinate):errors.append(problem('C08',label+'/coordinate','Pointer action needs an in-image integer point.'))
            if 'x' in args and 'y' in args and coordinate!=[args['x'],args['y']]:errors.append(problem('C08',label+'/coordinate','Action point differs from tool arguments.'))
        elif coordinate:errors.append(problem('C08',label+'/coordinate','Non-pointer action retains a coordinate; legacy sample conflict is diagnostic, not a required convention.'))
        if bbox is not None and not boxok(bbox):errors.append(problem('C08',label+'/target_bbox','Box invalid/out of viewport.'))
        if t in CONTROL and tree:
            e=elements.get(ac['target_element_id'])
            if not e:errors.append(problem('C07',label+'/target_element_id','No such element in this step tree.'))
            else:
                if ac['target_text']!=e['text']:errors.append(problem('C07',label+'/target_text','Action name differs from exact synchronized tree text; original example can itself contain this defect.'))
                if bbox is not None and bbox!=e['bbox']:errors.append(problem('C08',label+'/target_bbox','Action and tree boxes differ.'))
                if t=='type' and not e['inputable']:errors.append(problem('C09',label+'/target_element_id','Type target does not accept input.'))
                if ac.get('target_control_type') and ac['target_control_type']!=e['element_type']:observations.append(problem('I02',label+'/target_control_type','Control type names differ; no closed element enum is supplied.'))
            if bbox is None:errors.append(problem('C08',label+'/target_bbox','Control action requires box for documented target verification.'))
            elif t in POINTER and pointok(coordinate) and not(bbox[0]<=coordinate[0]<bbox[2] and bbox[1]<=coordinate[1]<bbox[3]):errors.append(problem('C08',label+'/coordinate','Point is outside target box.'))
        if t not in CONTROL and t!='hotkey' and (ac['target_element_id'] or ac['target_text']):errors.append(problem('C09',label,'Non-control action must not name/reference a control.'))
        if t=='type' and ac['input_text']!=args.get('text'):errors.append(problem('C09',label+'/input_text','Typed text differs from tool arguments.'))
        if t=='hotkey' and isinstance(args.get('keys'),list) and ac['input_text']!='+'.join(x for x in args['keys'] if isinstance(x,str)):errors.append(problem('C09',label+'/input_text','Hotkey text differs from keys.'))
        if t=='hotkey':
            try:
                canonical_keys = canonical_windows_keys(args.get('keys'), a['device_info'].get('os_name'))
            except ValueError:
                errors.append(problem('C09',label+'/tool_call/arguments/keys','WINDOWS_SHORTCUT_MAPPING_REQUIRED: hotkey must use declared Windows key names and an unambiguous platform mapping.'))
            else:
                if args['keys'] != canonical_keys:
                    errors.append(problem('C09',label+'/tool_call/arguments/keys','Hotkey delivery must use canonical Windows keys; raw capture keys stay unchanged.'))
                if ac['input_text'] != '+'.join(canonical_keys):
                    errors.append(problem('C09',label+'/input_text','Hotkey delivery input_text must match the canonical Windows keys.'))
                if ac['target_text'] != windows_key_label(canonical_keys):
                    errors.append(problem('C09',label+'/target_text','Hotkey delivery target_text must use the canonical Windows display names.'))
        if t=='hotkey' and (not ac['target_text'].strip() or ac['target_element_id'] or 'target_bbox' in ac):
            errors.append(problem('C09',label+'/target_text','Hotkey must name the key/combination and must not reference a control or box.'))
        if t not in ('type','hotkey') and ac['input_text']:errors.append(problem('C09',label+'/input_text','Non-input action has input_text.'))
        if t=='drag':
            end=ac.get('end_coordinate',[])
            if not pointok(end) or end!=[args.get('end_x'),args.get('end_y')]:errors.append(problem('C08',label+'/end_coordinate','Drag end differs from arguments or is out of image.'))
        if st['tool_result']['status']!='success' or st['tool_result']['error']:errors.append(problem('C10',label+'/tool_result','Delivery operation must succeed without errors.'))
        if i<n and 'screen_changed' not in st['tool_result']['return_value']:errors.append(problem('C01',label+'/tool_result/return_value','screen_changed required when next screenshot exists.'))
        if t=='complete' and (i!=n or args.get('status')!='success'):errors.append(problem('C10',label,'Successful complete must be final step.'))
        texts={k:st[k] for k in ['page_name','user_goal','next_step_rationale','step_result']};texts.update({k:ac[k] for k in ['precondition','expected_result']})
        for k,v in texts.items():
            if not re.search(r'[\u4e00-\u9fff]',v):errors.append(problem('C12',label+'/'+k,'Narrative has no Chinese characters; full language/semantic acceptance remains UNKNOWN.'))
            forbidden=prohibited_narrative(v)
            if forbidden:errors.append(problem('C12',label+'/'+k,'Explicitly prohibited machine/process text: '+', '.join(forbidden)))
        for reason in step_observation_issues(st['step_result']):
            errors.append(problem('C12',label+'/step_result',reason+'; Annex A requires the actual post-action observation.'))
    if a['steps'][-1]['action']['action_type']!='complete':errors.append(problem('C10','steps','Missing explicit final complete.'))
    if a['terminal_type']=='Web' and a.get('final_state_image')!=a['steps'][-1]['image_path']:errors.append(problem('C10','final_state_image','Web delivery final image must link to final screenshot, including when the field is absent or empty.'))
    if a.get('short_flow') is True and (effective>=5 or not a.get('short_flow_reason','').strip()):errors.append(problem('C11','short_flow','Short-flow declaration must describe fewer than five effective actions with a nonempty reason.'))
    actual={str(p.relative_to(directory)) for p in directory.rglob('*') if p.is_file() or p.is_symlink()}
    for extra in sorted(actual-expected):errors.append(problem('C05',extra,'Extra file inside sample.'))
    for child in directory.rglob('*'):
        if child.is_symlink():errors.append(problem('C05',child.relative_to(directory),'Symlink inside sample.'))
        elif child.is_dir() and child.relative_to(directory).as_posix() not in ['images','ui_tree']:
            errors.append(problem('C05',child.relative_to(directory),'Extra directory inside sample, including empty directories.'))
    for k in ['task_instruction','final_result','completion_judgement']:
        if not re.search(r'[\u4e00-\u9fff]',a[k]):errors.append(problem('C12',k,'Narrative contains no Chinese characters.'))
        forbidden=prohibited_narrative(a[k])
        if forbidden:errors.append(problem('C12',k,'Prohibited machine/process text: '+', '.join(forbidden)))
    titles=_task_titles_outside_corner_quotes(a['task_instruction'])
    if titles:errors.append(problem('C12','task_instruction',
        'Requirement §6 task titles outside quoted original text must use 「」 instead of 《》.',
        unquoted_book_titles=titles))
    return {'sample_path':str(directory),'sample_id':a['sample_id'],'confirmed_format_pass':not errors,'errors':errors,'observations':observations,'unknown_rule_ids':['U01','U02','U03','U04'],'customer_acceptance':'UNKNOWN','total_steps':n,'effective_steps':effective,'images':images,'source_identity':a['trajectory_source'],'action_sequence':[(st['action']['action_type'],st['action']['target_text'],st['page_name']) for st in a['steps']]}

def batch_check(batch,samples,layout=None):
    errors=[];observations=[];batch=Path(batch);csvp=batch/'metadata.csv';docs={name:(batch/name).is_file() for name in ['metadata.csv','qc_report.md','SHA256SUMS']}
    for k,v in docs.items():
        if not v:errors.append(problem('C13',batch/k,'Required batch delivery file missing.'))
    if csvp.is_file():
        try:
            with csvp.open(newline='',encoding='utf-8-sig') as f:reader=csv.DictReader(f);fields=reader.fieldnames;rows=list(reader)
            if fields is None or set(CSV_FIELDS)-set(fields):errors.append(problem('C13',csvp,'Metadata is missing documented field names.',actual_columns=fields))
            if fields and set(fields)-set(CSV_FIELDS):observations.append(problem('I02',csvp,'Additional metadata columns: customer acceptance UNKNOWN.',extra_columns=sorted(set(fields)-set(CSV_FIELDS))))
            if fields!=CSV_FIELDS:observations.append(problem('I02',csvp,'Column order differs from illustrated order; exact ordering acceptance UNKNOWN.'))
            ids=[x.get('sample_id') for x in rows];expected={x.get('sample_id') for x in samples}
            if len(ids)!=len(set(ids)) or set(ids)!=expected:errors.append(problem('C13',csvp,'CSV row/sample IDs do not reconcile.'))
            for row in rows:
                match=next((s for s in samples if s.get('sample_id')==row.get('sample_id')),None)
                if match and 'total_steps' in match:
                    a=load(Path(match['sample_path'])/'annotation.json')
                    expectedrow={'app_name':a['app_info']['app_name'],'task_instruction':a['task_instruction'],'completion_status':a['completion_status'],'steps':str(len(a['steps'])),'bytes':str(sum(p.stat().st_size for p in Path(match['sample_path']).rglob('*') if p.is_file()))}
                    for k,v in expectedrow.items():
                        if row.get(k)!=v:errors.append(problem('C13',str(csvp)+'/'+a['sample_id']+'/'+k,'CSV value differs from actual sample.'))
                    for k,v in [('task_type',a['task_type']),('screen_resolution',a['device_info']['screen_resolution']),('actions',[s['action']['action_type'] for s in a['steps']])]:
                        try:parsed=json.loads(row[k])
                        except (ValueError,KeyError):observations.append(problem('I02',str(csvp)+'/'+a['sample_id']+'/'+k,'Not JSON-array encoding. Customer CSV serialization not defined; cannot determine acceptance.'));continue
                        if parsed!=v:errors.append(problem('C13',str(csvp)+'/'+a['sample_id']+'/'+k,'Decoded metadata differs from actual sample.'))
        except (OSError,ValueError,csv.Error) as e:errors.append(problem('C13',csvp,str(e)))
    if docs['SHA256SUMS']:
        checked_manifest=verify_manifest(batch)
        for message in checked_manifest['errors']:errors.append(problem('C13',batch/'SHA256SUMS',message))
    ground_truth_checked=0
    for sample in samples:
        if 'sample_id' not in sample:continue
        sid=sample['sample_id'];gp=layout.ground_truth(Path(sample['sample_path'])) if layout else batch/'evidence'/sid/'ground_truth.json'
        try:
            a=load(Path(sample['sample_path'])/'annotation.json');expected=[{'step_id':st['step_id'],'element_id':st['action']['target_element_id'],'text':st['action']['target_text'],'bbox':st['action'].get('target_bbox')} for st in a['steps'] if st['action']['action_type'] in CONTROL]
            if load(gp)!=expected:errors.append(problem('C14',gp,'Target truth archive differs from delivered control annotations.'))
            else:ground_truth_checked+=1
        except (OSError,ValueError,TypeError,KeyError) as e:errors.append(problem('C14',gp,'Required target truth archive missing/invalid: '+str(e)))
    return {'batch':str(batch),'required_delivery_files':docs,'ground_truth_samples_checked':ground_truth_checked,'confirmed_batch_contract_pass':not errors,'errors':errors,'observations':observations,'unknown_rule_ids':['U01','U02','U05'],'customer_acceptance':'UNKNOWN'}

def observations_from_examples(root):
    data=defaultdict(lambda:{'types':set(),'observed_values':set(),'example_ids':set()})
    def walk(x,p,sid):
        t='boolean' if type(x)is bool else 'integer' if type(x)is int else 'number' if type(x)is float else 'string' if isinstance(x,str) else 'array' if isinstance(x,list) else 'object' if isinstance(x,dict) else 'null';d=data[p];d['types'].add(t);d['example_ids'].add(sid)
        if not isinstance(x,(dict,list)):d['observed_values'].add(json.dumps(x,ensure_ascii=False))
        if isinstance(x,dict):
            for k,v in x.items():walk(v,p+'/'+k,sid)
        if isinstance(x,list):
            for v in x:walk(v,p+'/*',sid)
    for path in sorted(root if isinstance(root,list) else Path(root).glob('*/annotation.json')):
        walk(load(path),'annotation',path.parent.name)
        for tree in sorted((path.parent/'ui_tree').glob('*.json')):walk(load(tree),'ui_tree',path.parent.name)
    return [{'path':p,'types':sorted(d['types']),'observed_distinct_value_count':len(d['observed_values']),'observed_values_preview':sorted(d['observed_values'])[:8],'examples':sorted(d['example_ids']),'certainty':'observed_only_NOT_closed_enum_or_requiredness','warning':'Observed values never become hard constants/enums without a prose rule.'} for p,d in sorted(data.items())]

def run(repo,dataset):
    repo=Path(repo) if repo is not None else None;dataset=Path(dataset);layout=discover(dataset);paths=layout.annotations;samples=[sample_check(p.parent) for p in paths];batches=[]
    for batch in layout.batches:batches.append(batch_check(batch,[s for s in samples if layout.batch_for(Path(s['sample_path']))==batch],layout))
    ids=[s.get('sample_id') for s in samples];package_errors=[problem('C05',dataset,message) for message in layout.errors]
    if layout.kind=='customer-flat':
        for name in ['evidence','provenance','reviews','manifest.json','candidate_manifest.json','source_manifest.json','selection-provenance.json']:
            if (dataset/name).exists():package_errors.append(problem('C05',dataset/name,'Internal capture/review/provenance artifacts belong outside the customer package.'))
        annex_b=dataset/'附件B-动作空间与坐标系.md';authority_b=repo/B if repo is not None else None
        if not annex_b.is_file():package_errors.append(problem('C14',annex_b,'Original Annex B is required in the customer package.'))
        elif authority_b is not None and authority_b.is_file() and sha(annex_b)!=sha(authority_b):package_errors.append(problem('C14',annex_b,'Original Annex B differs from the archived authority; put additions in the separate system-prompt document.'))
        prompt=dataset/'动作空间与系统提示.md';prompt_text=prompt.read_text() if prompt.is_file() else ''
        for sample in samples:
            dtype=sample.get('source_identity',{}).get('data_type')
            if dtype and not re.search(r'^#{1,6}\s+'+re.escape(dtype)+r'\s*$',prompt_text,re.M):
                package_errors.append(problem('C14',prompt,'Missing system-prompt chapter named for data_type: '+dtype,sample_id=sample.get('sample_id')))
    # Required document roles, not guessed exclusive customer filenames.
    choices=package_document_paths(dataset)
    declared={}
    for declaration in ['document_roles.json','candidate_manifest.json']:
        if (dataset/declaration).is_file():
            try:
                raw=load(dataset/declaration);mapping=raw.get('document_roles',{}) if isinstance(raw,dict) else None
                if not isinstance(mapping,dict):raise ValueError('document_roles must be an object')
                declared.update(mapping)
            except (OSError,ValueError,TypeError) as e:package_errors.append(problem('C14',dataset/declaration,str(e)))
    role_results={}
    for role,options in choices.items():
        if role in declared:
            try:
                found=declared[role];file=safe_path(dataset,found)
                if not file.is_file() or not file.stat().st_size:raise ValueError('Declared document missing or empty')
                role_results[role]={'path':found,'status':'PASS','scope':'existence_only_not_semantic_acceptance'}
            except (OSError,ValueError,TypeError) as e:
                role_results[role]={'path':declared[role],'status':'FAIL'};package_errors.append(problem('C14',dataset,str(e)+': '+role))
        else:
            found=next((rel for rel in options if (dataset/rel).is_file() and (dataset/rel).stat().st_size),None)
            role_results[role]={'path':found,'status':'PASS' if found else 'REVIEW_REQUIRED','scope':'existence_only_not_semantic_acceptance'}
    # Missing conventional names alone do not prove a missing role: the
    # customer's prose does not prescribe exclusive filenames for these docs.
    if not paths:package_errors.append(problem('C05',dataset,'No sample annotations found under samples/<id>/ or <batch>/samples/<id>/.'))
    if len(ids)!=len(set(ids)):package_errors.append(problem('C15','sample_id','Duplicate IDs within inspected package.'))
    exact=defaultdict(set)
    for s in samples:
        for im in s.get('images',[]):exact[im['sha256']].add(s.get('sample_id'))
    duplicate_groups=[{'rule_id':'C17','sha256':h,'sample_ids':sorted(ids),'occurrences':[{'sample_id':s['sample_id'],'step':im['step'],'path':str(Path(s['sample_path'])/f'images/step_{im["step"]:03}.png')} for s in samples for im in s.get('images',[]) if im['sha256']==h]} for h,ids in exact.items() if len(ids)>1]
    pairs=sorted({tuple(sorted((x,y))) for g in duplicate_groups for x in g['sample_ids'] for y in g['sample_ids'] if x<y})
    return {'tool':VERSION,'customer_program_executed':False,'authority':'archived prose + original examples, not internally fixed M1 constants','dataset':str(dataset),'layout':layout.kind,'sample_count':len(samples),'confirmed_sample_format_pass':sum(s['confirmed_format_pass'] for s in samples),'confirmed_sample_format_fail':sum(not s['confirmed_format_pass'] for s in samples),'confirmed_sample_issue_count':sum(len(s['errors']) for s in samples),'batch_count':len(batches),'confirmed_batch_contract_fail':sum(not b['confirmed_batch_contract_pass'] for b in batches),'confirmed_batch_issue_count':sum(len(b['errors']) for b in batches),'package_errors':package_errors,'document_roles':role_results,'samples':samples,'batches':batches,'exact_cross_sample_image_groups':duplicate_groups,'confirmed_duplicate_pair_count':len(pairs),'confirmed_duplicate_pairs':[list(p) for p in pairs],'confirmed_quality_pass':not duplicate_groups,'exact_duplicate_note':'Customer §6 route-1 potential rejection evidence; no near-duplicate algorithm or global adjudication executed. Pilot is not full production delivery.','unknown_rules':[r for r in catalog() if r['certainty']=='unknown'],'inferred_rules':[r for r in catalog() if r['certainty']=='inferred'],'customer_acceptance':'UNKNOWN','delivery_ready':False,'no_replay_requirement':{'source':CL+'#验收范围','M1_replay_missing_is_not_customer_format_blocker':True}}

def field_contract_matrix():
    rows=[]
    def walk(schema,path,required):
        rule='C03' if '/task_type' in path else 'C04' if '/trajectory_source/' in path else 'C08' if path.endswith(('/coordinate','/target_bbox','/end_coordinate','/bbox','/screen_resolution')) else 'C09' if path.endswith(('/action_type','/tool_name')) else 'C02' if 'enum' in schema else 'C01'
        constraints={k:v for k,v in schema.items() if k not in ('properties','items','required','additionalProperties')}
        rows.append({'field_path':path,'required':required,'constraints':constraints,'rule_id':rule,'certainty':'explicit_archived_contract','source':A+('#界面树文件' if path.startswith('ui_tree') else '#字段表与通用约定'),'actual_customer_machine_rule':'UNKNOWN'})
        for key,sub in schema.get('properties',{}).items():walk(sub,path+'/'+key,key in schema.get('required',[]))
        if 'items' in schema:walk(schema['items'],path+'/*',True)
    walk(ANNOTATION,'annotation',True);walk(TREE,'ui_tree',True)
    return rows

def authority_registry(repo):
    out=[]
    for rel,kind in [(CL,'project-user-confirmed clarification, overrides conflicting archived prose'),(REQ,'archived client requirement; external current version not independently verified'),(A,'archived client field specification'),(B,'archived client action specification'),(EX,'example guidance; acknowledges historical defects'),('projects/prd/M1-规则说明.md','internal engineering rule; NOT client validator authority')]:
        path=repo/rel;text=path.read_text();out.append({'path':rel,'sha256':sha(path),'authority':kind,'headings':[{'line':i,'heading':line} for i,line in enumerate(text.splitlines(),1) if line.startswith('#')],'customer_executable':False})
    return out

def main():
    ap=argparse.ArgumentParser(description=__doc__);ap.add_argument('--repo',type=Path,required=True);ap.add_argument('--dataset',type=Path,required=True);ap.add_argument('--output',type=Path,required=True);args=ap.parse_args()
    if args.output.resolve().is_relative_to(args.dataset.resolve()):raise ValueError('Report must be outside the inspected dataset.')
    args.output.mkdir(parents=True,exist_ok=False)
    report=run(args.repo,args.dataset);examples=args.repo/'request/web操作采集需求/samples';report['original_examples']=[sample_check(p.parent) for p in sorted(examples.glob('*/annotation.json'))]
    report['original_example_deep_diagnostics']={'not_acceptance':True,'temporary_in_memory_waiver':'Only task_type minItems=0 to expose known historic deeper defects; no inputs/schema files changed.','samples':[sample_check(p.parent,True) for p in sorted(examples.glob('*/annotation.json'))]}
    report['authority_registry']=authority_registry(args.repo)
    report['existing_internal_quality_layer']={'source':str(args.repo/'verify_results/quality-goal-20261022-followup/receipt.json'),'report_sha256':sha(args.repo/'verify_results/quality-goal-20261022-followup/receipt.json'),'existing_results':load(args.repo/'verify_results/quality-goal-20261022-followup/receipt.json'),'note':'Reused prior internal evidence; not rerun, not customer rules, not customer acceptance. Prior M1 replay blocker is superseded for client acceptance by clarification.'}
    report['program_discovery']={'scope':'project request files + project source/schema/scripts/prd; excludes installed dependencies and generated copies','customer_executable_found':False,'customer_machine_schema_found':False,'internal_validator':'projects/code/webcollect/validate.py','internal_schemas':'projects/code/webcollect/schemas','discovery_limit':'No claim about inaccessible customer systems or files outside this project.'}
    (args.output/'field-contract-matrix.json').write_text(json.dumps(field_contract_matrix(),ensure_ascii=False,indent=2)+'\n')
    (args.output/'report.json').write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n')
    (args.output/'rule-catalog.json').write_text(json.dumps(catalog(),ensure_ascii=False,indent=2)+'\n')
    (args.output/'example-field-observations.json').write_text(json.dumps(observations_from_examples(examples),ensure_ascii=False,indent=2)+'\n')
    (args.output/'annotation.proxy.schema.json').write_text(json.dumps(ANNOTATION,ensure_ascii=False,indent=2)+'\n');(args.output/'ui_tree.proxy.schema.json').write_text(json.dumps(TREE,ensure_ascii=False,indent=2)+'\n')
    print(json.dumps({k:v for k,v in report.items() if k not in ['samples','batches','original_examples']},ensure_ascii=False,indent=2))
    return 1 if report['confirmed_sample_format_fail'] or report['confirmed_batch_contract_fail'] or report['package_errors'] or not report['confirmed_quality_pass'] else 2 # 2 = no known format errors, customer acceptance UNKNOWN
if __name__=='__main__':raise SystemExit(main())
