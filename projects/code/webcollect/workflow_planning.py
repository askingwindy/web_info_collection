"""Source-bound model proposals; compilation/collection remain deterministic."""
import json
from .planning import verify_evidence
from .batch_core import load_json

VERSION='source-workflow-planning-2-explicit-keyboard'
# The existing compiler is authoritative for nested action/anchor contracts.
FIELDS={'capability_id':'string','capability_version':'string','task_family':'string','initial_url':'string',
        'instruction':'string','task_type':'array','operations':'array','subgoals':'array',
        'required_actions':'array','final_assertions':'array','final_result':'string',
        'completion_judgement':'string','anchors':'array'}
SCHEMA={'type':'object','properties':{'tasks':{'type':'array','items':{'type':'object',
    'properties':{key:({'type':kind,'items':{}} if kind=='array' else {'type':kind}) for key,kind in FIELDS.items()},
    'required':list(FIELDS),'additionalProperties':False}}},'required':['tasks'],'additionalProperties':False}


def prompt_for(capability):
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
            'notes':'type只执行keyboard.insert_text，绝不会自动聚焦、全选或清空。必须显式规划click聚焦；原值非空时再hotkey keys=[meta,a]全选，然后type替换。两个非空必要输入通常构成6个真实操作，这些不是凑步。每个operation.subgoal_id必须等于subgoals中的实际id，不得拼接不存在id。final_assertions必须包含任务要求的具体结果值或范围，不能仅contains=BMI等标题。required_actions列出必要operation_id字符串。task_family使用capability.task_families已有值。macOS聚焦后整体替换已有输入用hotkey keys=[meta,a]，空值不全选。不要添加complete操作，采集器自动生成终态。不要把示例占位符复制进任务。最多返回一个独立任务。'},
        'capability':capability,'anchors':anchors}


def propose(gateway, job, capability, *, synthetic_response=None):
    prompt=prompt_for(capability)
    refs=[ref for anchor in prompt['anchors'] for ref in anchor.values()]
    verify_evidence(refs)
    from .telemetry import phase
    with phase(gateway.ledger.path.parent/'planning-phases.jsonl','workflow_planning',scope={'job_id':job['id']}):
        response=gateway.call(job,VERSION,json.dumps(prompt,ensure_ascii=False),SCHEMA,
            images=[anchor['image']['path'] for anchor in prompt['anchors']],synthetic_response=synthetic_response)
    for spec in response['tasks']:
        if spec.get('anchors')!=prompt['anchors']:raise ValueError('Model changed original page evidence bindings')
    return response
