"""Source-bound model proposals; compilation/collection remain deterministic."""
import json
from .planning import verify_evidence
from .batch_core import load_json

VERSION='source-workflow-planning-3-operation-contract'
# The existing compiler is authoritative for nested action/anchor contracts.
FIELDS={'capability_id':'string','capability_version':'string','task_family':'string','initial_url':'string',
        'instruction':'string','task_type':'array','operations':'array','subgoals':'array',
        'required_actions':'array','final_assertions':'array','final_result':'string',
        'completion_judgement':'string','anchors':'array'}
SCHEMA={'type':'object','properties':{'tasks':{'type':'array','items':{'type':'object',
    'properties':{key:({'type':kind,'items':{}} if kind=='array' else {'type':kind}) for key,kind in FIELDS.items()},
    'required':list(FIELDS),'additionalProperties':False}}},'required':['tasks'],'additionalProperties':False}

# Paid model responses must satisfy the actual operation envelope before compilation.
_OPERATION={'type':'object','properties':{
    **{k:{'type':'string','minLength':1} for k in ('operation_id','subgoal_id','action_type','goal','rationale','expected','selector')},
    'index':{'type':'integer','minimum':0},'arguments':{'type':'object'},'execution':{'type':'object'},
    'evidence':{'type':'object'},'postconditions':{'type':'array','minItems':1,'items':{'type':'object'}}},
    'required':['operation_id','subgoal_id','action_type','goal','rationale','expected'],
    'additionalProperties':False,
    'allOf':[{'if':{'properties':{'action_type':{'enum':['click','double_click','right_click','drag','select','type']}}},
              'then':{'required':['selector','evidence']}}]}
SCHEMA['properties']['tasks']['items']['properties']['operations']={'type':'array','minItems':5,'maxItems':10,'items':_OPERATION}
from importlib.resources import files
SCHEMA['properties']['tasks']['items']['properties']['task_type']=json.loads(files('webcollect').joinpath('schemas/annotation.schema.json').read_text())['properties']['task_type']


def legacy_prompt_for(capability):
    anchors=[page.get('page_anchor') for page in capability['capabilities']]
    if not all(anchors):raise ValueError('Workflow planning requires original page anchors')
    verify_evidence([ref for anchor in anchors for ref in anchor.values()])
    states=[load_json(anchor['state']['path']) for anchor in anchors]
    if any(not state.get('capture_controls') for state in states):raise ValueError('Source lacks observed selector bindings; recapture only under explicit authorization')
    return {'observed_states':states,'version':VERSION,'instruction':
        '根据实际可见控件和原始证据生成结构化工作流。优先自然5至8个必要操作，最多10个；wait/complete不计数，不得凑步、虚构控件或仅换参数。'
        '每步绑定operation_id/subgoal_id、selector、evidence.anchor_index/anchor_element_id/target_label，声明必要性及可见终态final_assertions。'
        'selector必须原样使用observed_states.capture_controls中的绑定；anchors必须原样使用给定引用。无法完成返回空tasks；所有提案都要经过程序校验和独立后置QC。',
         'contract_examples':{
            'operation':{'operation_id':'input-value','subgoal_id':'input','action_type':'type','selector':'COPY_OBSERVED_SELECTOR','arguments':{'text':'desired value'},'goal':'填写任务要求的值','rationale':'完成必要输入','expected':'显示输入值','evidence':{'anchor_index':0,'anchor_element_id':'COPY_OBSERVED_ELEMENT_ID','target_label':'COPY_VISIBLE_LABEL'},'postconditions':[{'selector':'COPY_OBSERVED_SELECTOR','value':'desired value'}]},
            'subgoal':{'id':'input','description':'填写必要输入','evidence':[{'operation_id':'input-value','postcondition_index':0}]},
            'result_subgoal':{'id':'result','description':'核对结果','evidence':[{'final_assertion_index':0}]},
            'final_assertions':[{'selector':'COPY_OBSERVED_RESULT_SELECTOR','contains':'expected visible result'}],
            'notes':'postconditions省略或使用非空数组；断言只允许selector加value/contains/number/numbers/checked/disabled之一，或visible_text。禁止focused断言、禁止在operation里放final_assertions。task_type必须用中文枚举（填写表单、数据查看、搜索查询等），不能英文。每个控件操作都必须提供独立selector字段，不能只放在postconditions里。type只执行keyboard.insert_text，绝不会自动聚焦、全选或清空。必须显式规划click聚焦；原值非空时再hotkey keys=[meta,a]全选，然后type替换。两个非空必要输入通常构成6个真实操作，这些不是凑步。每个operation.subgoal_id必须等于subgoals中的实际id，不得拼接不存在id。final_assertions必须包含任务要求的具体结果值或范围，不能仅contains=BMI等标题。required_actions列出必要operation_id字符串。task_family使用capability.task_families已有值。macOS聚焦后整体替换已有输入用hotkey keys=[meta,a]，空值不全选。不要添加complete操作，采集器自动生成终态。不要把示例占位符复制进任务。最多返回一个独立任务。'},
        'capability':capability,'anchors':anchors}


# The old envelope above remains importable for validating archived proposals.
from .workflow_normalization import prompt_for, SCHEMA as SEMANTIC_SCHEMA, VERSION as SEMANTIC_VERSION


def propose(gateway, job, capability, *, synthetic_response=None, compiler_feedback=None, fragment=False, context=None):
    schema, version = SEMANTIC_SCHEMA, SEMANTIC_VERSION
    if fragment:
        from .fragment_workflow import prompt_for as fragment_prompt, SCHEMA as schema, VERSION as version
        prompt = fragment_prompt(capability, context)
    else:
        prompt=prompt_for(capability)
    if compiler_feedback:prompt['compiler_feedback']=compiler_feedback
    anchors=[p['page_anchor'] for p in capability['capabilities']]
    from .telemetry import phase
    with phase(gateway.ledger.path.parent/'planning-phases.jsonl','workflow_planning',scope={'job_id':job['id']}):
        response=gateway.call(job,version,json.dumps(prompt,ensure_ascii=False),schema,
            images=[anchor['image']['path'] for anchor in anchors],synthetic_response=synthetic_response,attempts=1,
            output_limit=min(8192,gateway.ledger.config['model']['max_completion_tokens']))
    for spec in response['tasks']:
        if 'anchors' in spec and spec['anchors']!=anchors:raise ValueError('Model changed original page evidence bindings')
    return response


def validate_feedback(ledger,capability,feedback):
    from .planning import object_sha256,verify_evidence
    if set(feedback)!={'schema_version','prior_job_id','generation_result'} or feedback['schema_version']!='webcollect-workflow-compiler-feedback-1':
        raise ValueError('Versioned bounded compiler feedback required')
    verify_evidence([feedback['generation_result']]);report=load_json(feedback['generation_result']['path'])
    job=ledger.get(feedback['prior_job_id'])
    with ledger.connect() as con:
        states=[r[0] for r in con.execute('SELECT state FROM model_requests WHERE job_id=?',(job['id'],))]
    if (job['kind']!='task-generation' or job['state']!='done' or job['payload'].get('workflow_feedback_sha256') or
        job['payload'].get('capability_sha256')!=object_sha256(capability) or not states or any(s!='succeeded' for s in states) or
        report.get('generated_tasks')!=0 or report.get('pending') or not report.get('rejected')):
        raise ValueError('Only one revision of a successful but compiler-rejected proposal; UNKNOWN cannot be revised')
    specs=job['result']['specs']['tasks']
    if not specs or {object_sha256(s) for s in specs}!={r.get('spec_sha256') for r in report['rejected']}:
        raise ValueError('Compiler feedback must cover the original rejected specifications')
    from .workflow_proposal import compile_workflow
    from .fragment_workflow import compile_fragment
    def compile_for(spec):
        if spec.get('schema_version')=='webcollect-fragment-workflow-1':
            return compile_fragment(capability,spec,'compiler-feedback-check')
        return compile_workflow(capability,spec,'compiler-feedback-check')
    for spec in specs:
        try:compile_for(spec)
        except ValueError as error:
            if not any(r['spec_sha256']==object_sha256(spec) and r['reason']==str(error) for r in report['rejected']):raise ValueError('Compiler feedback reason changed')
        else:raise ValueError('Cannot revise a valid plan through rejection feedback')
    fragments=any(spec.get('schema_version')=='webcollect-fragment-workflow-1' for spec in specs)
    instruction=('仅修正以下明确编译错误。输入、替换或清空输入框一律用set_value并给value；'
                 '折线下方控件必须先滚动露出再操作；保持5至8个实际动作，不要凑步；'
                 '无法自然达到5步返回空tasks及结构化原因。本协议最多修订一次，仍需完整重新编译与冻结。'
                 if fragments else
                 '仅修正以下明确编译错误。已满足的条件保留为前置断言、不计动作；不要凑步。无法自然达到5步返回空tasks及结构化原因。本协议最多修订一次，仍需完整重新编译与冻结。')
    return {'instruction':instruction,'prior_specs':specs,'rejections':report['rejected'],'binding':feedback}
