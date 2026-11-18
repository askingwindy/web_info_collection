"""确定性结构检查；图文语义和真实采集证据始终单独待审。"""
from webcollect import workspace_json as json
import re
from datetime import datetime
from pathlib import Path
from PIL import Image
from jsonschema import Draft202012Validator, validators
from importlib.resources import files

SCHEMAS = files('webcollect').joinpath('schemas')
StrictValidator = validators.extend(Draft202012Validator, type_checker=Draft202012Validator.TYPE_CHECKER.redefine('integer', lambda checker, value: type(value) is int))
POINTER = {'click', 'double_click', 'right_click', 'scroll', 'drag', 'select'}
CONTROL = {'click', 'double_click', 'right_click', 'type', 'drag', 'select'}
NONCONTROL = {'scroll', 'wait', 'back', 'open_url', 'complete'}
NARRATIVE = ['page_name', 'user_goal', 'next_step_rationale', 'step_result']
PENDING = ['截图真实性、视口范围及截图与界面树同步证据', '控件与页面语言一致、叙述为简体中文',
           '标注简体中文、完整性及可见证据一致性', '动作连续性、无凑步及最终任务完成',
           '账号来源与业务操作合规', '四路及跨批去重', '人工看图核对']

def read_json(path):
    return json.loads(path.read_text(encoding='utf-8'), parse_constant=lambda value: (_ for _ in ()).throw(ValueError('非标准 JSON 常量 '+value)))

def validate_sample(directory, mode='delivery', manifest=None):
    directory = Path(directory).resolve()
    issues = []
    def fail(code, path, message): issues.append({'code':code,'path':path,'message':message})
    def schema_check(data, name, prefix):
        schema = json.loads(SCHEMAS.joinpath(f'{name}.schema.json').read_text(encoding='utf-8'))
        errors = list(StrictValidator(schema).iter_errors(data))
        for e in errors:
            fail('schema', prefix + '/' + '/'.join(map(str,e.absolute_path)), e.message)
        return not errors
    def load(path, label):
        try: return read_json(path)
        except (OSError, ValueError, UnicodeError, RecursionError) as e:
            fail('json',label,str(e)); return None
    def safe_file(relative, label):
        try:
            p = directory / relative
            if '\x00' in relative or Path(relative).is_absolute() or not p.resolve().is_relative_to(directory):
                fail('path_escape',label,'必须是样本目录内的相对路径'); return None
            if not p.is_file(): fail('missing_file',label,relative); return None
            return p
        except (OSError, ValueError, RuntimeError) as e:
            fail('path_escape',label,str(e)); return None
    def point_ok(p, res): return 0 <= p[0] < res[0] and 0 <= p[1] < res[1]
    def box_ok(b, res): return 0 <= b[0] < b[2] <= res[0] and 0 <= b[1] < b[3] <= res[1]
    def inside(p,b): return b[0] <= p[0] < b[2] and b[1] <= p[1] < b[3]
    def image_check(p, res, label):
        try:
            with Image.open(p) as im:
                if im.format != 'PNG' or list(im.size) != res: fail('image',label,'必须为 PNG 且分辨率与样本一致')
                im.verify()
            with Image.open(p) as im: im.load()
        except (OSError, ValueError, SyntaxError, Image.DecompressionBombError) as e: fail('image',label,str(e))
    annotation_path = safe_file('annotation.json','annotation.json')
    data = load(annotation_path,'annotation.json') if annotation_path else None
    valid = schema_check(data,'annotation','annotation')
    effective = 0
    if mode not in ('integration','delivery'): raise ValueError('未知检查模式')
    if manifest is not None:
        manifest_valid = schema_check(manifest,'manifest','manifest')
        if manifest_valid:
            if isinstance(data,dict) and data.get('sample_id') not in manifest['samples']:
                fail('provenance','manifest/samples','样本编号未登记在批次清单中')
            site_ids=[site['site_id'] for site in manifest['sites']]
            uris=[site['uri'] for site in manifest['sites']]
            if isinstance(data,dict) and str(data.get('sample_id','')).split('_sample_')[0] not in site_ids:
                fail('provenance','manifest/sites','缺少该样本站点映射')
            if len(set(site_ids))!=len(site_ids) or len(set(uris))!=len(uris):
                fail('provenance','manifest/sites','站点编号或 URI 重复')
    if mode == 'delivery':
        if any('integration' in p.name.lower() for p in (directory, *directory.parents)) or (isinstance(data,dict) and '联调' in str(data.get('task_instruction',''))):
            fail('integration_data','sample','明确标记的联调数据不能进入交付检查')
        if not isinstance(manifest,dict) or manifest.get('sample_kind') != 'real':
            fail('provenance','manifest','交付检查必须提供 sample_kind=real 的批次清单；声明不替代证据核验')
        else:
            for key in ['batch_id','program_version','rule_version','sites']:
                if not manifest.get(key): fail('provenance','manifest/'+key,'缺少批次追踪信息')
            if isinstance(data,dict):
                sid = str(data.get('sample_id','')).split('_sample_')[0]
                sites = manifest.get('sites',[])
                if not isinstance(sites,list) or not any(isinstance(s,dict) and s.get('site_id') == sid and s.get('uri') and s.get('site_category') for s in sites):
                    fail('provenance','manifest/sites','缺少该样本站点的 URI 及类目映射')
    if valid:
        res = data['device_info']['screen_resolution']
        if directory.name != data['sample_id']: fail('sample_id','sample_id','样本编号必须等于目录名')
        expected = {'annotation.json'}
        ids = set()
        steps = data['steps']
        effective = sum(s['action']['action_type'] not in ('wait','complete') for s in steps)
        from .closing_policy import annotation_errors
        for error in annotation_errors(data):fail('collection_ending','steps',error)
        if effective < 5 and (data.get('short_flow') is not True or not data.get('short_flow_reason','').strip()):
            fail('effective_steps','steps','少于 5 个有效操作步，必须标记短流程并说明原因')
        if data.get('short_flow') is True and (effective >= 5 or not data.get('short_flow_reason','').strip()):
            fail('short_flow','short_flow','短流程须确实少于 5 个有效步且有原因')
        if data['completion_status'] == 'failed': fail('completion','completion_status','失败轨迹不能交付')
        for i,s in enumerate(steps,1):
            label=f'steps/{i}'
            a,c,t = s['action'],s['tool_call'],s['action']['action_type']
            args=c['arguments']
            if s['step_id'] != i: fail('step_sequence',label,'step_id 必须从 1 连续编号')
            for key,relative in [('image_path',f'images/step_{i:03}.png'),('ui_tree_path',f'ui_tree/step_{i:03}.json')]:
                if s[key] != relative: fail('file_sequence',label+'/'+key,'应为 '+relative)
                expected.add(relative)
            pic=safe_file(s['image_path'],label+'/image_path')
            if pic: image_check(pic,res,label+'/image_path')
            tree_path=safe_file(s['ui_tree_path'],label+'/ui_tree_path')
            tree=load(tree_path,label+'/tree') if tree_path else None
            elements={}
            if tree_path and schema_check(tree,'ui_tree',label+'/tree'):
                if tree['image_path'] != s['image_path'] or tree['screen_resolution'] != res:
                    fail('tree_sync',label,'界面树图片引用或分辨率不一致')
                for e in tree['elements']:
                    eid=e['element_id']
                    if eid in elements or eid == 'root': fail('element_id',label,'重复或保留元素编号 '+eid)
                    elements[eid]=e
                    if not box_ok(e['bbox'],res): fail('bbox',label+'/tree/'+eid,'元素框必须位于视口内且面积大于零')
                    if not e['visible']: fail('visibility',label+'/tree/'+eid,'只收可见元素')
                for eid,e in elements.items():
                    parent=e['parent_id']
                    seen={eid}
                    while parent != 'root':
                        if parent not in elements: fail('parent',label+'/tree/'+eid,'父元素不存在'); break
                        if parent in seen: fail('parent',label+'/tree/'+eid,'父元素引用成环'); break
                        seen.add(parent); parent=elements[parent]['parent_id']
            if c['tool_name'] != t:
                fail('tool_name',label,'工具名与动作类型不一致')
                continue
            if c['call_id'] in ids: fail('call_id',label,'调用编号重复')
            ids.add(c['call_id'])
            if c['timestamp']:
                try:
                    dt=datetime.fromisoformat(c['timestamp'].replace('Z','+00:00'))
                    if dt.tzinfo is None: raise ValueError('须包含时区')
                except ValueError: fail('timestamp',label,'时间戳须为带时区的 ISO 8601，未知时留空')
            if s['tool_result']['status'] != 'success' or s['tool_result']['error']:
                fail('tool_result',label,'交付步骤必须成功且无错误信息')
            if i < len(steps) and 'screen_changed' not in s['tool_result']['return_value']:
                fail('screen_changed',label,'存在后继截图时必须记录界面是否变化')
            if t in POINTER:
                p=a['coordinate']
                if len(p)!=2 or not point_ok(p,res): fail('coordinate',label,'触点必须是视口内两个整数')
                if all(k in args for k in ('x','y')) and p != [args['x'],args['y']]: fail('coordinate',label,'触点与工具参数不一致')
            elif a['coordinate']: fail('coordinate',label,'无触点动作 coordinate 应为 []')
            b=a.get('target_bbox')
            if b is not None and not box_ok(b,res): fail('bbox',label,'目标框无效')
            if t in CONTROL:
                e=elements.get(a['target_element_id'])
                if not e: fail('target_reference',label,'控件动作须引用同步界面树中的元素')
                else:
                    if a['target_text'] != e['text']: fail('target_text',label,'控件文字与界面树不一致')
                    if b != e['bbox']: fail('target_bbox',label,'目标框与界面树不一致')
                    if a.get('target_control_type') and a['target_control_type'] != e['element_type']: fail('target_control_type',label,'控件类型不一致')
                    if not e['enabled']: fail('target_state',label,'目标控件不可用')
                    if t=='type' and not e['inputable']: fail('target_state',label,'输入目标不支持输入')
                if b is None: fail('bbox',label,'控件动作必须提供目标框')
                if t in POINTER and b and len(a['coordinate'])==2 and not inside(a['coordinate'],b): fail('coordinate_bbox',label,'触点必须落在目标框内')
            if t in NONCONTROL and (a['target_element_id'] or a['target_text'] or b is not None or a.get('target_control_type')):
                fail('noncontrol',label,'非控件动作的目标编号及文字须为空，并省略目标框和类型')
            if t=='hotkey' and (a['target_element_id'] or b is not None or a.get('target_control_type') or not a['target_text']):
                fail('hotkey',label,'按键名必填，不引用控件或目标框')
            if t=='drag':
                end=a.get('end_coordinate')
                if end is None or not point_ok(end,res) or end != [args.get('end_x'),args.get('end_y')]: fail('drag_end',label,'拖动终点缺失、越界或参数不一致')
            elif 'end_coordinate' in a: fail('end_coordinate',label,'只有 drag 提供终点')
            if t=='type':
                if a['input_text'] != args.get('text'): fail('input_text',label,'输入文本与工具参数不一致')
            elif t=='hotkey':
                if a['input_text'] != '+'.join(args.get('keys',[])): fail('input_text',label,'按键须与 keys 以 + 连接的结果一致')
            elif a['input_text']: fail('input_text',label,'非输入按键动作 input_text 应为空')
            if t=='complete' and (i != len(steps) or args.get('status') != 'success'):
                fail('complete',label,'仅允许末步 complete 且 status=success；异常是否可交付另行语义裁决')
            texts=[s[k] for k in NARRATIVE]+[a['precondition'],a['expected_result']]+s['exception_evidence']
            for value in texts:
                if not re.search(r'[\u4e00-\u9fff]',value): fail('narrative',label,'叙述字段须含中文，语义另行核验')
                if re.search(r'DOM|XPath|红圈|蓝框|触点|按既定流程|回放|脚本|%[0-9A-Fa-f]{2}',value): fail('narrative',label,'出现禁止的采集术语或编码片段')
        if steps[-1]['action']['action_type'] != 'complete': fail('complete','steps','末步必须 complete')
        final=data.get('final_state_image','')
        if final != steps[-1]['image_path']: fail('final_image','final_state_image','末步为 complete 时终态图必须指向末步截图')
        actual={str(p.relative_to(directory)) for p in directory.rglob('*') if p.is_file() or p.is_symlink()}
        for extra in sorted(actual-expected): fail('extra_file',extra,'样本内不允许多余文件')
        for key in ['task_instruction','final_result','completion_judgement']:
            if not re.search(r'[\u4e00-\u9fff]',data[key]): fail('narrative',key,'叙述字段须含中文')
            if re.search(r'DOM|XPath|红圈|蓝框|触点|按既定流程|回放|脚本|%[0-9A-Fa-f]{2}',data[key]): fail('narrative',key,'出现禁止的采集术语或编码片段')
    return {'rule_version':'1.0.0','mode':mode,'sample_id':data.get('sample_id') if isinstance(data,dict) else None,
            'structural_pass':not issues,'delivery_ready':False,'total_steps':len(data['steps']) if valid else None,
            'effective_steps':effective if valid else None,'issues':issues,'pending_checks':PENDING,
            'note':'联调样本不得计入交付；结构通过不代表语义或交付验收通过。'}
