"""Observed form capabilities -> validated M4 plans -> existing production runtime.

The default uses registered numeric business strategies without model access.
The existing model-to-text/number compiler remains an explicit option.
Unsupported or naturally short workflows remain rejected candidates, never
padded or allocated an ID. Parameter/route changes are not new business tasks.
"""
import asyncio
import hashlib
import re
from contextlib import closing
import unicodedata
from decimal import Decimal, InvalidOperation
import json
from pathlib import Path
import sqlite3
import time
from urllib.parse import urlsplit, urlunsplit

from .batch_core import BudgetStop, BatchLedger, file_sha, load_json, save_json
from .planning import canonical, object_sha256, timestamp, validate_capability
from .bmi_strategy import ADAPTER_ID as BMI_ADAPTER_ID, bmi_spec
from .date_strategy import ADAPTER_ID as DATE_ADAPTER_ID, date_spec

VERSION = 'observed-form-compiler-5-date-difference'
STRATEGY_VERSION = 'deterministic-business-widgets-3-date'
FORMAL_LATEST_PATH = Path(__file__).resolve().parents[3] / 'results/delivery/LATEST.md'

# These are deliberately narrow business strategies, not generic guesses about
# arbitrary forms. Result values are rechecked by the existing saved-frame
# assertions; visual/semantic readiness remains a separate review requirement.
STRATEGIES = (
    {'id':'shopping-total-v1', 'forms':('购物金额计算','购物合计','购物总额计算'),
     'fields':(('数量','商品数量'),('单价','商品单价')), 'values':(6,7),
     'submit':('计算合计','计算总额'), 'result':'购物合计', 'unit':'元', 'operator':'multiply'},
    {'id':'travel-speed-v1', 'forms':('速度计算','平均速度计算'),
     'fields':(('距离（千米）','路程（千米）'),('耗时（小时）','时间（小时）')), 'values':(60,2),
     'submit':('计算速度','计算平均速度'), 'result':'平均速度', 'unit':'千米/小时', 'operator':'divide'},
    {'id':'rectangle-area-v1', 'forms':('矩形面积计算','长方形面积计算'),
     'fields':(('长度（厘米）','长（厘米）'),('宽度（厘米）','宽（厘米）')), 'values':(6,7),
     'submit':('计算面积',), 'result':'矩形面积', 'unit':'平方厘米', 'operator':'multiply'},
)


def strict_object(properties):
    return {'type':'object','properties':properties,'required':list(properties),'additionalProperties':False}


TEXT = {'type':'string','minLength':1}
INPUT_SCHEMA = strict_object({'selector':TEXT,'label':TEXT,'value':TEXT})
SPEC_SCHEMA = strict_object({'tasks':{'type':'array','items':strict_object({
    'page_uri':TEXT,'form_label':TEXT,'goal':TEXT,
    'inputs':{'type':'array','minItems':2,'items':INPUT_SCHEMA},
    'submit':strict_object({'selector':TEXT,'label':TEXT}),
    'completion':strict_object({'selector':TEXT,'contains':TEXT})})}})


def task_signature(task):
    """Conservative: argument/keyword substitutions have the same identity."""
    controls = [(op.get('action_type'), op.get('selector'), op.get('index',0))
                for op in task.get('operations',[]) if op.get('action_type') not in ('wait','complete','scroll','hotkey')]
    return object_sha256({'site':_page_identity(task['site_uri']),
                         'page':_page_identity(task['initial_url']),'controls':controls})


def _page_identity(uri):
    parsed=urlsplit(uri)
    return urlunsplit((parsed.scheme.lower(),parsed.netloc.lower(),parsed.path or '/','',''))


def semantic_signature(task):
    strategy=task.get('deterministic_strategy',{}).get('id')
    if not strategy:
        # Earlier E2 tasks have no strategy metadata. Recover only an exact
        # registered role/submit match, never free-text similarity as proof.
        operations=task.get('operations',[])
        labels={op.get('evidence',{}).get('target_label') for op in operations if op.get('action_type')=='type'}
        submits={op.get('evidence',{}).get('target_label') for op in operations if op.get('action_type')=='click'}
        matches=[item['id'] for item in STRATEGIES if len(labels)==2 and
                 all(len(labels & set(role))==1 for role in item['fields']) and submits & set(item['submit'])]
        strategy=matches[0] if len(matches)==1 else None
    if not strategy:
        return None
    # For this narrow strategy set, a second calculator on the same origin is
    # still the same business task even on a different URI/path. More capacity
    # requires an independently defined business strategy, not another route.
    parsed=urlsplit(task['site_uri'])
    return object_sha256({'origin':urlunsplit((parsed.scheme.lower(),parsed.netloc.lower(),'','','')),
                         'strategy':strategy})


def deterministic_specs(capability):
    specs, rejected = [], []
    for page in capability['capabilities']:
        rejected.extend({'site_uri':capability['site_uri'], **item}
                        for item in page.get('widget_rejections', []))
        for widget in page.get('widgets', []):
            strategy = {BMI_ADAPTER_ID: bmi_spec, DATE_ADAPTER_ID: date_spec}.get(widget.get('adapter_id'))
            if strategy is None:
                rejected.append({'site_uri':capability['site_uri'], 'page_uri':page['page_uri'],
                                 'reason':'No registered adapter for observed non-form widget'})
                continue
            try:
                specs.append(strategy(capability, page, widget, STRATEGY_VERSION))
            except (ValueError, KeyError, TypeError, InvalidOperation) as error:
                rejected.append({'site_uri':capability['site_uri'], 'page_uri':page['page_uri'],
                                 'adapter_id':widget.get('adapter_id'), 'reason':str(error)})
        for form in page['forms']:
            identity={'site_uri':capability['site_uri'],'page_uri':page['page_uri'],'form_label':form['label']}
            matches=[strategy for strategy in STRATEGIES if form['label'] in strategy['forms']]
            if len(matches)!=1:
                rejected.append({**identity,'reason':'No registered deterministic business strategy; do not invent a completion oracle'})
                continue
            strategy=matches[0]
            try:
                fields=[field for field in form['fields'] if field['visible']]
                inputs=[]
                for aliases,value in zip(strategy['fields'],strategy['values']):
                    bound=[field for field in fields if field['label'] in aliases and
                           field['tag']=='input' and field['type']=='number']
                    if len(bound)!=1:
                        raise ValueError('Strategy requires one exact visible numeric field for each business role')
                    target=bound[0]
                    for bound_name,comparison in (('min',lambda actual,limit:actual>=limit),('max',lambda actual,limit:actual<=limit)):
                        if target.get(bound_name) not in ('',None) and not comparison(Decimal(value),Decimal(target[bound_name])):
                            raise ValueError('Strategy value outside observed field '+bound_name)
                    inputs.append({'selector':target['selector'],'label':target['label'],'value':str(value)})
                editable=[field for field in fields if field['tag'] in ('input','textarea','select') and
                          field['type'] not in ('submit','button','reset','hidden')]
                if len(editable)!=len(inputs):
                    raise ValueError('Additional form inputs require a separately verified business strategy')
                submit=[field for field in fields if field['type'] in ('submit','button') and field['label'] in strategy['submit']]
                if len(submit)!=1 or len(page.get('result_targets',[]))!=1:
                    raise ValueError('Strategy needs one exact submit control and one unambiguous observed result container')
                left,right=strategy['values']
                expected=left*right if strategy['operator']=='multiply' else left//right
                if strategy['operator']=='divide' and (not right or left%right):
                    raise ValueError('This strategy only supports an exact integer result')
                title=page['title']
                goal=('在「'+title+'」中将「'+inputs[0]['label']+'」填写为'+inputs[0]['value']+'、将「'+
                      inputs[1]['label']+'」填写为'+inputs[1]['value']+'，点击「'+submit[0]['label']+'」并核对'+
                      strategy['result']+'为'+str(expected)+strategy['unit']+'。')
                specs.append({'page_uri':page['page_uri'],'form_label':form['label'],'goal':goal,'inputs':inputs,
                    'submit':{'selector':submit[0]['selector'],'label':submit[0]['label']},
                    'completion':{'selector':page['result_targets'][0]['selector'],'number':expected,
                                  'description':strategy['result']+'为'+str(expected)+strategy['unit']},
                    'deterministic_strategy':{'id':strategy['id'],'version':STRATEGY_VERSION,
                        'business_goal':strategy['result'],'operator':strategy['operator'],
                        'observed_roles':[item['label'] for item in inputs],
                        'assurance':'registered strategy proposal; actual saved-frame assertions and independent QC still required'}})
            except (ValueError,KeyError,TypeError,InvalidOperation) as error:
                rejected.append({**identity,'strategy_id':strategy['id'],'reason':str(error)})
    if not specs and not rejected:
        rejected.append({'site_uri':capability['site_uri'],'reason':'No observed forms'})
    return {'tasks':specs,'strategy_rejections':rejected}


def register_task(ledger, task, job_id):
    """Use the existing index atomically for structural and business identities."""
    keys=[task_signature(task)]
    semantic=semantic_signature(task)
    if semantic:
        keys.append('semantic:'+semantic)
    with ledger.transaction() as con:
        for signature in keys:
            old=con.execute('SELECT job_id,task_json FROM generated_task_index WHERE signature=?',(signature,)).fetchone()
            if old and (old['job_id']!=job_id or json.loads(old['task_json'])!=task):
                raise ValueError('Business goal or form/action structure already generated; parameter/selector substitutions rejected')
        for signature in keys:
            con.execute('INSERT OR IGNORE INTO generated_task_index VALUES(?,?,?)',(signature,job_id,canonical(task)))


def read_history(registry):
    if not registry:
        return []
    path = Path(registry).resolve()
    if not path.is_file():
        raise ValueError('Historical registry missing; never create an empty production replacement')
    with closing(sqlite3.connect(path.as_uri()+'?mode=ro',uri=True)) as con:
        exists = con.execute("SELECT 1 FROM sqlite_master WHERE name='m4_tasks'").fetchone()
        return [json.loads(row[0]) for row in con.execute('SELECT task_json FROM m4_tasks')] if exists else []


def _origin(uri):
    p = urlsplit(uri)
    if p.scheme not in ('http', 'https') or not p.hostname or p.username or p.password:
        raise ValueError('Historical source must be an explicit public HTTP(S) URI')
    return urlunsplit((p.scheme.lower(), p.netloc.lower(), '', '', ''))


def annotation_business_strategy(annotation):
    """Recover only registered business roles plus their actual ordered actions.

    Task names, prose keywords and parameter values alone are not identities.
    Unknown business types stay unknown, including reading about BMI.
    """
    def label(value):
        return ''.join(unicodedata.normalize('NFKC', str(value)).split()).lower()
    inputs, clicks = [], []
    for index, step in enumerate(annotation.get('steps', [])):
        action, tool = step.get('action', {}), step.get('tool_call', {})
        kind = action.get('action_type')
        if tool.get('tool_name') != kind or step.get('tool_result', {}).get('status') != 'success':
            continue
        if kind == 'type' and action.get('target_control_type') in ('input', 'textarea'):
            if str(action.get('input_text', '')).strip():
                inputs.append((index, label(action.get('target_text', ''))))
        if kind == 'click' and action.get('target_control_type') == 'button':
            clicks.append((index, label(action.get('target_text', ''))))
    strategies = list(STRATEGIES) + [{
        'id': 'body-mass-index-v1',
        'fields': (('身高 (cm)', '身高（cm）'), ('体重 (kg)', '体重（kg）')),
        'submit': ('计算 BMI',)}]
    matched = []
    for strategy in strategies:
        roles = [{label(v) for v in aliases} for aliases in strategy['fields']]
        # Exactly two editable business roles; selectors/values do not create novelty.
        if len(inputs) != 2 or not all(sum(v in role for _, v in inputs) == 1 for role in roles):
            continue
        if any(index > max(i for i, _ in inputs) and target in {label(v) for v in strategy['submit']}
               for index, target in clicks):
            matched.append(strategy['id'])
    return matched[0] if len(matched) == 1 else None


def _history_package_files(root):
    """Match qc-cumulative-set-1 hashes without parsing any review judgments."""
    files = {}
    for path in sorted(root.rglob('*')):
        if path.is_symlink():
            raise ValueError('Frozen historical packages cannot contain symlinks')
        if path.is_file():
            digest = hashlib.sha256()
            with path.open('rb') as stream:
                for chunk in iter(lambda: stream.read(1024 * 1024), b''):
                    digest.update(chunk)
            files[path.relative_to(root).as_posix()] = digest.hexdigest()
    return files


def read_customer_history(manifest_path):
    """Read an explicit frozen customer population, never review/AI decisions."""
    manifest_path = Path(manifest_path).resolve()
    manifest_sha = file_sha(manifest_path)
    manifest = load_json(manifest_path)
    if (manifest.get('schema_version') != 'qc-cumulative-set-1'
            or not isinstance(manifest.get('packages'), list) or not manifest['packages']):
        raise ValueError('Real generation needs a nonempty frozen qc-cumulative-set-1 history')
    roots, records, packages, seen = [], [], [], set()
    for item in manifest['packages']:
        root = Path(item['path'])
        root = (manifest_path.parent / root).resolve() if not root.is_absolute() else root.resolve()
        if not root.is_dir() or root in roots or any(root.is_relative_to(r) or r.is_relative_to(root) for r in roots):
            raise ValueError('Historical package roots missing, repeated or overlapping')
        roots.append(root)
        expected = item.get('package_files_sha256')
        if not isinstance(expected, dict) or not expected or _history_package_files(root) != expected:
            raise ValueError('Frozen historical package files/SHA changed: ' + str(root))
        listing = load_json(root / 'site-list.json')
        if listing.get('schema_version') != 'webcollect-site-list-1':
            raise ValueError('Historical package needs customer site-list source identities')
        sites = {v['site_id']: v for v in listing['sites']}
        assignments = {v['sample_id']: v['site_id'] for v in listing['samples']}
        annotations = sorted((root / 'samples').glob('*/annotation.json'))
        ids = {path.parent.name for path in annotations}
        if (not ids or len(sites) != len(listing['sites']) or len(assignments) != len(listing['samples'])
                or set(assignments) != ids):
            raise ValueError('Historical sample/site population must match exactly once')
        for site_id, site in sites.items():
            members = site.get('sample_ids', [])
            if len(members) != len(set(members)) or set(members) != {sid for sid, owner in assignments.items() if owner == site_id}:
                raise ValueError('Historical source membership mismatch')
        for path in annotations:
            annotation = load_json(path); sid = annotation.get('sample_id')
            if sid != path.parent.name or sid in seen or assignments[sid] not in sites:
                raise ValueError('Historical sample identity missing, repeated or misassigned')
            seen.add(sid); site = sites[assignments[sid]]
            strategy = annotation_business_strategy(annotation)
            records.append({'sample_id': sid, 'annotation_path': str(path),
                'annotation_sha256': expected[path.relative_to(root).as_posix()],
                'site_uri': site['uri'], 'origin': _origin(site['uri']),
                'strategy_id': strategy, 'classification': 'KNOWN_STRATEGY' if strategy else 'UNKNOWN_REQUIRES_COMPARISON',
                'semantic_signature': semantic_signature({'site_uri': site['uri'],
                    'deterministic_strategy': {'id': strategy}}) if strategy else None})
        # Reject concurrent package drift while parsing the frozen annotation population.
        if _history_package_files(root) != expected:
            raise ValueError('Historical package changed while reading: ' + str(root))
        packages.append({'path': str(root), 'files': len(expected), 'sample_count': len(annotations),
                         'package_files_sha256': object_sha256(expected)})
    if file_sha(manifest_path) != manifest_sha:
        raise ValueError('Historical set manifest changed while reading')
    scope = {'schema_version': 'webcollect-task-history-scope-1',
        'manifest': {'path': str(manifest_path), 'sha256': manifest_sha},
        'packages': packages, 'package_count': len(packages), 'customer_samples': len(records),
        'known_strategy_samples': sum(r['strategy_id'] is not None for r in records),
        'unknown_strategy_samples': sum(r['strategy_id'] is None for r in records),
        'parsed_content': 'original annotations and site-list only; no AI/human judgments',
        'coverage': manifest.get('scope', 'explicit supplied customer packages; not an inferred complete universe')}
    return records, scope


def bind_formal_history(scope):
    """Require this repository's explicit current formal delivery, not an arbitrary set."""
    latest = FORMAL_LATEST_PATH.resolve()
    before = file_sha(latest)
    targets = set()
    for link in re.findall(r'\]\(([^)]+)\)', latest.read_text()):
        link = link.strip('<>')
        if not link.endswith('/README.md') or '://' in link:
            continue
        path = Path(link)
        path = (latest.parent / path).resolve() if not path.is_absolute() else path.resolve()
        if path.parent.parent == latest.parent and path.is_file() and (path.parent / 'samples').is_dir():
            targets.add(path.parent)
    if len(targets) != 1 or file_sha(latest) != before:
        raise ValueError('Formal LATEST package missing, ambiguous or changed; cannot establish history coverage')
    required = targets.pop()
    if str(required) not in {p['path'] for p in scope['packages']}:
        raise ValueError('Frozen history omits current formal LATEST package: ' + str(required))
    return {**scope, 'formal_anchor': {'path': str(latest), 'sha256': before,
                                     'required_package': str(required)}}


def check_live_m4_history(plan, registry, output):
    """Refresh current M4 business identities before dispatch; own bound resume only."""
    from .collect_runtime import runtime_scope
    registry, capture = Path(registry).resolve(), Path(output).resolve() / 'capture'
    own_scope = runtime_scope(capture)
    own_tasks = set()
    with closing(sqlite3.connect(registry.as_uri()+'?mode=ro', uri=True)) as con:
        tables = {row[0] for row in con.execute("SELECT name FROM sqlite_master WHERE type='table'")}
        if 'm4_tasks' not in tables:
            return {'m4_tasks_checked': 0, 'own_resume_tasks': 0}
        columns = {row[1] for row in con.execute('PRAGMA table_info(m4_tasks)')}
        rows = list(con.execute('SELECT '+('scope_id' if 'scope_id' in columns else 'NULL')+',task_json FROM m4_tasks'))
        bootstrap_path = capture / 'bootstrap.json'
        if bootstrap_path.is_file() and 'm4_plans' in tables:
            bootstrap = load_json(bootstrap_path)
            bound = list(con.execute('SELECT plan_json FROM m4_plans WHERE scope_id=?', (own_scope,)))
            original_plan = {k:v for k,v in plan.items() if k!='media_preflight'}
            bootstrap_plan = bootstrap.get('plan', {})
            if (bootstrap.get('schema_version') != 'webcollect-bootstrap-m4-1'
                    or bootstrap.get('output_path') != str(capture)
                    or bootstrap.get('registry_path') != str(registry)
                    or bootstrap.get('manifest', {}).get('runtime_scope_id') != own_scope
                    or {k:v for k,v in bootstrap_plan.items() if k!='media_preflight'} != original_plan
                    or len(bound)!=1 or json.loads(bound[0][0]) != bootstrap_plan):
                raise ValueError('M4 resume is not bound to this exact output/scope/plan')
            own_tasks = {object_sha256(t) for t in bootstrap_plan['tasks']}
        for task in plan['tasks']:
            signature, semantic = task_signature(task), semantic_signature(task)
            for scope_id, value in rows:
                old = json.loads(value)
                if scope_id == own_scope and object_sha256(old) in own_tasks and old == task:
                    continue
                if task_signature(old) == signature or semantic and semantic_signature(old) == semantic:
                    raise ValueError('Current M4 history contains the same business/structure outside this exact bound resume; no dispatch')
    return {'m4_tasks_checked': len(rows), 'own_resume_tasks': len(own_tasks)}


def customer_history_decision(task, records):
    """Known same business rejects; unresolved same-origin comparisons hold."""
    semantic = semantic_signature(task)
    matches = [r for r in records if semantic and r['semantic_signature'] == semantic]
    if matches:
        return {'status': 'REJECTED', 'reason': 'Same registered business in frozen customer history; parameter/path substitutions are not new tasks',
                'history_sample_ids': [r['sample_id'] for r in matches], 'strategy_id': task.get('deterministic_strategy', {}).get('id')}
    unresolved = [r for r in records if r['origin'] == _origin(task['site_uri']) and r['strategy_id'] is None]
    if not semantic or unresolved:
        return {'status': 'REVIEW_REQUIRED', 'reason': 'Business novelty cannot be determined against frozen customer history',
                'history_sample_ids': [r['sample_id'] for r in unresolved]}
    return None


def compile_form(capability, spec):
    from .collect import validate_plan
    from .task_instruction import validate_task_instruction
    inventories = [page for page in capability['capabilities'] if page['page_uri']==spec['page_uri']]
    if not inventories:
        raise ValueError('Task starting page absent from observed capability')
    if spec.get('widget_adapter'):
        forms = [widget for page in inventories for widget in page.get('widgets', [])
                 if widget.get('adapter_id') == spec['widget_adapter'] and widget.get('label') == spec['form_label']]
        strategy = {BMI_ADAPTER_ID: bmi_spec, DATE_ADAPTER_ID: date_spec}.get(spec['widget_adapter'])
        if strategy is None or len(forms) != 1 or len(inventories) != 1:
            raise ValueError('Task must bind exactly one supported observed non-form widget')
        if strategy(capability, inventories[0], forms[0], STRATEGY_VERSION) != spec:
            raise ValueError('Widget task specification changed from the observed business strategy')
    else:
        forms = [f for page in inventories for f in page['forms'] if f['label']==spec['form_label']]
    if len(forms)!=1:
        raise ValueError('Task must bind exactly one observed form')
    fields = {f['selector']:f for f in forms[0]['fields'] if f['visible']}
    if len(fields)!=sum(f['visible'] for f in forms[0]['fields']):
        raise ValueError('Ambiguous form selectors')
    if len(spec['inputs'])<2:
        raise ValueError('Naturally short forms require a different strategy; do not pad to five actions')
    if len({f['selector'] for f in spec['inputs']})!=len(spec['inputs']):
        raise ValueError('Repeated input does not add a subgoal')
    operations, subgoals = [], []
    for number, request in enumerate(spec['inputs'],1):
        target = fields.get(request['selector'])
        if (not target or target['label']!=request['label'] or target['tag'] not in ('input','textarea')
                or target['type'] not in ('text','number','textarea','search','email','url','tel')):
            raise ValueError('Unsupported/unobserved form target or original visible label')
        if not isinstance(request['value'],str) or not request['value'].strip() or request['value']==target['value']:
            raise ValueError('Input is empty or already has the requested value; no useful state change')
        name = 'field-'+str(number)
        common = {'subgoal_id':name,'selector':request['selector'],
                  'evidence':{'target_label':target['label']}}
        operations.append({**common,'operation_id':name+'-focus','action_type':'click',
                           'goal':'选中「'+target['label']+'」','rationale':'填写该项前先聚焦输入位置',
                           'expected':'光标进入「'+target['label']+'」'})
        # insert_text appends; preexisting values need explicit selection first.
        if target['value']:
            operations.append({'operation_id':name+'-select','subgoal_id':name,'action_type':'hotkey',
                'arguments':{'keys':['meta','a']},'goal':'选中当前输入内容',
                'rationale':'原输入已有内容，需要整体替换','expected':'当前输入内容被选中'})
        operations.append({**common,'operation_id':name+'-type','action_type':'type',
            'arguments':{'text':request['value']},'goal':'将「'+target['label']+'」填写为「'+request['value']+'」',
            'rationale':'该值属于任务要求的必要输入','expected':'该输入框显示「'+request['value']+'」',
            'postconditions':[{'selector':request['selector'],'value':request['value']}]})
        subgoals.append({'id':name,'description':'填写「'+target['label']+'」',
                         'evidence':[{'operation_id':name+'-type','postcondition_index':0}]})
    submit = fields.get(spec['submit']['selector'])
    if not submit or submit['label']!=spec['submit']['label'] or submit['type'] not in ('submit','button'):
        raise ValueError('Submit target missing from actual form')
    results=[target for page in inventories for target in page.get('result_targets',[])
             if target['selector']==spec['completion']['selector']]
    if len(results)!=1:
        raise ValueError('Completion target absent/ambiguous in observed result containers')
    completion=spec['completion']
    if 'number' in completion:
        from .collect import check_numbers
        if type(completion['number']) is not int:
            raise ValueError('Deterministic completion requires an exact integer oracle')
        expected=completion['description']
        numeric={'count':1,'minimum':completion['number'],'maximum_exclusive':completion['number']+1,'integer':True}
        already_complete=check_numbers(results[0]['text'],numeric)
        final_assertions=[{'selector':completion['selector'],'numbers':numeric}]
        if spec.get('widget_adapter') == BMI_ADAPTER_ID:
            final_assertions.extend([
                {'selector':completion['selector'],'contains':spec['deterministic_strategy']['expected_display']},
                {'selector':'#resultContainer h2','contains':'您的 BMI 结果'}])
        elif spec.get('widget_adapter') == DATE_ADAPTER_ID:
            final_assertions.extend([
                {'selector':'#betweenDay','contains':'天'},
                {'selector':forms[0]['result_label_selector'],'contains':'相差'}])
    else:
        expected=completion['contains']
        if not isinstance(expected,str) or not expected.strip():
            raise ValueError('Empty completion is not a completion oracle')
        already_complete=expected in results[0]['text']
        final_assertions=[{'selector':completion['selector'],'contains':expected}]
    if already_complete:
        raise ValueError('Task result already visible before any operation; no padding allowed')
    operations.append({'operation_id':'submit','subgoal_id':'result','action_type':'click',
        'selector':submit['selector'],'evidence':{'target_label':submit['label']},
        'goal':'点击「'+submit['label']+'」','rationale':'输入完成后提交以得到所需结果',
        'expected':expected,'postconditions':final_assertions})
    subgoals.append({'id':'result','description':'核对实际显示的结果','evidence':[{'final_assertion_index':0}]})
    task = {'task_id':'form-'+object_sha256({'capability':capability['capability_id'],'spec':spec})[:24],
        'task_version':VERSION,'capability_id':capability['capability_id'],'capability_version':capability['version'],
        'task_family':'form-workflow','site_uri':capability['site_uri'],'site_category':capability['site_category'],
        'initial_url':spec['page_uri'],'app_name':inventories[0]['title'],'instruction':spec['goal'],
        'task_type':['填写表单'],'stop_when_final':True,'content_preparation':False,
        'operations':operations,'subgoals':subgoals,'required_actions':[op['operation_id'] for op in operations],
        'final_assertions':final_assertions,'final_result':expected,
        'completion_judgement':'核对最终截图中实际显示「'+expected+'」。'}
    if spec.get('deterministic_strategy'):
        task['deterministic_strategy']=spec['deterministic_strategy']
        task['capability_screen_status']=capability['status']
        task['capability_review_required']=capability['status']!='ready'
    validate_task_instruction(task['instruction'])
    validate_plan({'tasks':[task]})
    return task


def generate(ledger, catalog_path, output, *, history_registry=None, history_set=None, synthetic_specs=None, generator=None):
    from .task_contract import validate_m4_plan
    from .collect import validate_plan
    # Explicit fixture responses preserve the old controlled/model test API.
    # Ordinary API and CLI calls default to the no-model strategy path.
    generator=generator or ('model' if synthetic_specs is not None else 'deterministic')
    if generator not in ('deterministic','model'):
        raise ValueError('Unknown task generator')
    if generator=='model' and ledger.config.get('model') is None:
        raise ValueError('Model task generator requires an explicitly enabled model branch')
    if synthetic_specs is not None and (generator!='model' or ledger.config['mode']!='synthetic'):
        raise ValueError('Synthetic responses are only allowed by the explicit synthetic model fixture')
    catalog = load_json(catalog_path)
    if catalog.get('schema_version')!='webcollect-capability-catalog-1' or catalog.get('mode')!=ledger.config['mode']:
        raise ValueError('Capability catalog schema/mode mismatch')
    if ledger.config['mode']=='real' and history_registry is None:
        raise ValueError('Real generation must consult the existing production registry')
    if ledger.config['mode']=='real' and history_set is None:
        raise ValueError('Real generation requires --history-set with frozen customer packages; M4 registry alone is incomplete')
    customer_history, history_scope = read_customer_history(history_set) if history_set else ([], None)
    if ledger.config['mode']=='real':
        history_scope = bind_formal_history(history_scope)
    output = Path(output).resolve(); output.mkdir(parents=True,exist_ok=True)
    history = read_history(history_registry)
    history_hash = object_sha256({'m4_tasks': history, 'customer_history': history_scope})
    signatures = {task_signature(task) for task in history}
    semantics={semantic_signature(task) for task in history if semantic_signature(task)}
    tasks, rejected, pending, actual_prompts = [], [], [], []
    gateway=None
    if generator=='model':
        from .model_gateway import ModelGateway
        gateway=ModelGateway(ledger)
    for record in catalog['records']:
        try:
            validate_capability(record,require_ready=generator=='model')
            if record.get('status')=='rejected' or timestamp(record['expires_at'])<=time.time():
                raise ValueError('Capability rejected or expired')
            if record.get('mode')!=ledger.config['mode'] or 'form-workflow' not in record['task_families']:
                raise ValueError('No supported observed form workflow')
        except (ValueError,KeyError) as error:
            rejected.append({'site_uri':record.get('site_uri'),'reason':str(error)}); continue
        prompt = {'instruction':'Generate distinct natural tasks using the observed form inventory. Supply at least two different necessary text/number fields, the actual visible submit label, meaningful input values and a verifiable final visible result. Do not invent controls. Do not vary only parameters to create multiple tasks on one form. Unsupported forms yield no tasks. Use Chinese prose and 「」 for titles. Task execution rechecks all observations.',
                  'capability':{'site_uri':record['site_uri'],'pages':record['capabilities']}}
        if generator=='model':actual_prompts.append(prompt)
        jid = ledger.enqueue('task-generation', {'capability_sha256':object_sha256(record),'version':VERSION,
            'generator':generator,'strategy_version':STRATEGY_VERSION if generator=='deterministic' else None,
            'history_sha256':history_hash,'mode':ledger.config['mode']})
        try:
            job = ledger.claim('task-generation',job_id=jid)
        except BudgetStop as error:
            pending.append({'job_id':jid,'state':'budget_stopped','reason':str(error)}); break
        if not job:
            prior = ledger.get(jid)
            if prior['state']=='done':
                specs = prior['result']['specs']
            else:
                pending.append({'job_id':jid,'state':prior['state']}); continue
        else:
            try:
                specs=deterministic_specs(record) if generator=='deterministic' else gateway.call(
                    job,'task-generation-'+VERSION,json.dumps(prompt,ensure_ascii=False),SPEC_SCHEMA,
                    synthetic_response={'tasks':(synthetic_specs or {}).get(record['site_uri'],[])})
                ledger.finish(job,result={'specs':specs})
            except BudgetStop as error:
                ledger.finish(job,'queued',error=str(error)); pending.append({'job_id':jid,'state':'budget_stopped'}); break
            except Exception as error:
                ledger.finish(job,'review_required',error=type(error).__name__)
                pending.append({'job_id':jid,'state':'review_required'}); continue
        rejected.extend(specs.get('strategy_rejections',[]))
        for spec in specs['tasks']:
            try:
                task = compile_form(record,spec); signature=task_signature(task);semantic=semantic_signature(task)
                history_decision = customer_history_decision(task, customer_history) if history_scope else None
                if history_decision:
                    entry = {'site_uri': record['site_uri'], 'spec_sha256': object_sha256(spec), **history_decision}
                    (rejected if history_decision['status']=='REJECTED' else pending).append(entry)
                    continue
                if signature in signatures or semantic and semantic in semantics:
                    raise ValueError('Same business goal or form/action structure in history/current task set; parameter changes rejected')
                register_task(ledger,task,jid)
                signatures.add(signature)
                if semantic:semantics.add(semantic)
                tasks.append(task)
            except (ValueError,KeyError) as error:
                rejected.append({'site_uri':record['site_uri'],'spec_sha256':object_sha256(spec),'reason':str(error)})
    template=generator=='deterministic' or ledger.config['mode']=='synthetic'
    planning_stage=({'mode':'template','template_version':STRATEGY_VERSION,
        'description':'固定业务策略匹配实际控件标签与字段范围，确定性计算完成数值，再由原表单编译器生成操作；未调用模型。'}
        if generator=='deterministic' else
        {'mode':'template','template_version':'synthetic-controlled-task-response-1',
         'description':'合成适配器返回冻结任务规格，未进行真实模型调用。'} if ledger.config['mode']=='synthetic' else
        {'mode':'model','description':'根据实际能力库存生成表单任务，再按固定编译器生成显式操作。',
         'prompt':json.dumps(actual_prompts,ensure_ascii=False)})
    plan = {'schema_version':'webcollect-plan-m4-1','tasks':tasks,
        'generation':{'version':VERSION,'generator':generator,'strategy_version':STRATEGY_VERSION if generator=='deterministic' else None,
                      'catalog_sha256':file_sha(catalog_path),'history_sha256':history_hash,'history_scope':history_scope,
                      'mode':ledger.config['mode'],'synthetic_results_are_production':False,
                      'capability_review_required':any(task.get('capability_review_required') for task in tasks)},
        'production_facts':{'accounts_and_privacy':'仅使用公开无账号页面；任务中的输入为程序生成的测试值。' if ledger.config['mode']=='real' else '仅受控合成工程页面，无账号，不进入正式交付。',
            'narrative_generation':'采集器根据实际相邻截图和同步观察生成文字，必要修订沿用 narrative_revisions。',
            'narrative_mode':'template' if template else 'mixed','prompt_stages':{
                'planning':planning_stage,'narrative':{'mode':'template','template_version':'actual-state-describe_change',
                             'description':'沿用采集器实际可见状态及相邻截图对应的叙述生成。'}}}}
    if tasks:
        validate_m4_plan(plan); validate_plan(plan)
        save_json(output/'plan.json',plan)
    result={'schema_version':'webcollect-task-generation-summary-1','catalog_candidates':len(catalog['records']),
        'strategy_form_candidates':sum(len(page.get('forms',[])) for record in catalog['records'] for page in record.get('capabilities',[])),
        'strategy_widget_candidates':sum(len(page.get('widgets',[])) for record in catalog['records'] for page in record.get('capabilities',[])),
        'generated_tasks':len(tasks),'rejected':rejected,'pending':pending,'sample_ids_allocated':0,
        'plan_file':str(output/'plan.json') if tasks else None,'mode':ledger.config['mode'],'generator':generator,
        'capability_review_required':plan['generation']['capability_review_required'],
        'historical_tasks_consulted':len(history),'history_scope':history_scope,
        'historical_customer_samples_consulted':len(customer_history),'real_collection_executed':False}
    save_json(output/('generation-'+object_sha256(result)[:16]+'.json'),result)
    return result


async def execute(ledger, plan_path, catalog_path, output, registry, policy, *, resume=False):
    """Publish once, delegate all IDs/retry/inventory limits to collect_m4, export once."""
    from .preflight import preflight_plan
    from .planning import publish_plan
    from .collect_runtime import collect_m4
    from .production_facts import derive
    from .client_package import build_client_package
    from .collect import validate_plan
    from .navigation import BatchNavigation
    if ledger.config['mode']!='real':
        raise ValueError('Synthetic browser integration uses the controlled fixture runner, never a production CLI bypass')
    plan = load_json(plan_path); catalog = load_json(catalog_path)
    validate_plan(plan)
    if plan.get('generation',{}).get('mode')!='real' or catalog.get('mode')!='real':
        raise ValueError('Only real capability-generated tasks can enter production')
    history_scope = plan.get('generation', {}).get('history_scope')
    if not isinstance(history_scope, dict) or history_scope.get('schema_version') != 'webcollect-task-history-scope-1':
        raise ValueError('Real execution requires explicit frozen customer history coverage; regenerate legacy M4-only plans')
    history_manifest = history_scope.get('manifest', {})
    if file_sha(history_manifest['path']) != history_manifest.get('sha256'):
        raise ValueError('Historical set changed since task generation')
    customer_history, current_scope = read_customer_history(history_manifest['path'])
    current_scope = bind_formal_history(current_scope)
    if current_scope != history_scope:
        raise ValueError('Historical package population changed since task generation')
    for task in plan['tasks']:
        if customer_history_decision(task, customer_history):
            raise ValueError('Task duplicate or unresolved against frozen customer history; no preflight or allocation')
    if not Path(registry).is_file():
        raise ValueError('Existing production registry required; no empty replacement')
    check_live_m4_history(plan, registry, output)
    supplied_policy=load_json(policy)
    with sqlite3.connect(Path(registry).resolve().as_uri()+'?mode=ro',uri=True) as con:
        campaign=con.execute('SELECT policy_json FROM m4_campaigns WHERE campaign_id=?',
                             (supplied_policy.get('campaign_id'),)).fetchone()
        if not campaign:raise ValueError('Use an existing authorized production campaign; this wrapper never creates one')
        active_policy=json.loads(campaign[0])
        attempts=con.execute('SELECT COUNT(*) FROM m4_attempts WHERE campaign_id=?',(supplied_policy['campaign_id'],)).fetchone()[0]
        pending=con.execute("SELECT COUNT(*) FROM m4_tasks WHERE campaign_id=? AND status='collected_pending_review'",(supplied_policy['campaign_id'],)).fetchone()[0]
        if attempts>=active_policy['attempt_cap'] or pending>=active_policy['pending_review_cap']:
            raise BudgetStop('Existing campaign attempt/pending-review limit reached; no preflight or collection started')
    output = Path(output).resolve(); output.mkdir(parents=True,exist_ok=True)
    jid = ledger.enqueue('collection', {'plan_sha256':file_sha(plan_path),'catalog_sha256':file_sha(catalog_path),
        'registry':str(Path(registry).resolve()),'output':str(output),'policy_sha256':file_sha(policy)})
    prior=ledger.get(jid)
    if resume and prior['state']=='review_required' and (output/'capture/bootstrap.json').is_file():
        # Explicit --resume delegates reconciliation to collect_m4's immutable
        # bootstrap, source, committed-sample and original registry checks.
        with ledger.transaction() as con:
            con.execute("UPDATE jobs SET state='queued' WHERE id=? AND state='review_required'",(jid,))
            ledger.event(con,'collection_reconciliation_requested',{'job_id':jid})
    job = ledger.claim('collection',job_id=jid)
    if not job:
        return ledger.get(jid)
    navigation = BatchNavigation(ledger, job)
    async def renew():
        while True:
            await asyncio.sleep(2)
            ledger.heartbeat(job)
    async def work():
        pf=output/'preflight'; publication=output/'publication.json'
        if not publication.exists():
            if not (pf/'report.json').exists():
                ledger.consume('probe_pages',jid+':preflight',len(plan['tasks']))
                await preflight_plan(plan_path,pf,samples=2,interval_ms=100,preserve_order=True,navigation=navigation)
            scheduled=load_json(pf/'scheduled-plan.json')
            save_json(publication,publish_plan(scheduled,catalog))
        check_live_m4_history(plan, registry, output)
        result=await collect_m4(pf/'scheduled-plan.json',output/'capture',registry,
            publication_path=publication,policy_path=policy,resume=resume or (output/'capture/bootstrap.json').exists(),
            navigation=navigation)
        if result['collection_status']=='paused_pending_resume':
            return {'collection':result,'candidate':None,'stopped':'existing runtime paused; budget and queued work retained'}
        facts_path=output/'facts.json'; client=output/'candidate'
        if result.get('collected',0):
            save_json(facts_path,derive(output/'capture'))
            if not client.exists():
                build_client_package(Path(__file__).resolve().parents[3],output/'capture',client,facts=facts_path)
                save_json(output/'candidate-receipt.json',{'files_sha256':{
                    p.relative_to(client).as_posix():file_sha(p) for p in sorted(client.rglob('*')) if p.is_file()}})
            receipt=load_json(output/'candidate-receipt.json')
            actual={p.relative_to(client).as_posix():file_sha(p) for p in sorted(client.rglob('*')) if p.is_file()}
            if actual!=receipt['files_sha256']:raise ValueError('Existing customer candidate is incomplete or changed')
        return {'collection':result,'candidate':str(client) if client.exists() else None,
                'QC_approval':False,'human_review':'pending'}
    renewal=asyncio.create_task(renew());working=asyncio.create_task(work())
    try:
        done,_=await asyncio.wait((renewal,working),return_when=asyncio.FIRST_COMPLETED)
        if renewal in done:
            renewal.result();raise ValueError('Collection heartbeat unexpectedly stopped')
        result=await working
        ledger.finish(job,'queued' if result.get('stopped') else 'done',result=result);return result
    except BudgetStop as error:
        ledger.finish(job,'review_required' if (output/'capture/bootstrap.json').exists() else 'queued',error=str(error));raise
    except Exception as error:
        ledger.finish(job,'review_required',error=type(error).__name__); raise
    finally:
        for pending_task in (renewal,working):
            if not pending_task.done():pending_task.cancel()
        await asyncio.gather(renewal,working,return_exceptions=True)


def main(argv=None):
    import argparse
    parser=argparse.ArgumentParser(description=__doc__)
    sub=parser.add_subparsers(dest='command',required=True)
    for command in ('generate','execute'):
        p=sub.add_parser(command)
        for name in ('config','ledger','catalog','output'):
            p.add_argument('--'+name,type=Path,required=True)
        if command=='generate':
            p.add_argument('--history-registry',type=Path)
            p.add_argument('--history-set',type=Path,help='Frozen qc-cumulative-set-1 customer-package history; required in real mode')
            p.add_argument('--generator',choices=('deterministic','model'),default='deterministic',
                           help='Registered no-model strategies by default; model is an explicit budgeted option')
        else:
            for name in ('plan','registry','policy'):p.add_argument('--'+name,type=Path,required=True)
            p.add_argument('--resume',action='store_true')
    args=parser.parse_args(argv)
    try:
        ledger=BatchLedger(args.ledger,load_json(args.config))
        result=generate(ledger,args.catalog,args.output,history_registry=args.history_registry,history_set=args.history_set,generator=args.generator) if args.command=='generate' else asyncio.run(
            execute(ledger,args.plan,args.catalog,args.output,args.registry,args.policy,resume=args.resume))
        print(json.dumps(result,ensure_ascii=False,indent=2));return 0
    except (ValueError,OSError,KeyError,TypeError,sqlite3.Error) as error:
        print(json.dumps({'status':'STOP','reason':str(error)},ensure_ascii=False));return 2


if __name__=='__main__':raise SystemExit(main())
