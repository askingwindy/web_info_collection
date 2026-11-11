"""Ordinary result completion using the existing branch call and sealed results.

The model maps original business items to actual outputs; the host validates
source, submission causality and substantive values without calculating answers.
"""
from copy import deepcopy
from .batch_core import load_json
from .planning import object_sha256, verify_evidence
from .result_execution import result_execution_binding
from .numeric_result_evidence import substantive_result_text, match_result, process_field, process_result_text


from .plan_protocol import RESULT_COMPLETION_PROTOCOL

VERSION = RESULT_COMPLETION_PROTOCOL


def enabled(task):
    return task.get('fragment',{}).get('result_completion_protocol')==RESULT_COMPLETION_PROTOCOL


def schema(item):
    if isinstance(item,dict):
        props=item.get('properties',{})
        if 'choice' in props and 'plan' in props:
            props['result_answer']={'type':'object','additionalProperties':False,'required':['check_answers'],
                'properties':{'check_answers':{'type':'array','minItems':1,'items':{
                    'type':'object','additionalProperties':False,'required':['check_index','evidence_ids'],
                    'properties':{'check_index':{'type':'integer','minimum':0},
                        'evidence_ids':{'type':'array','minItems':1,'uniqueItems':True,'items':{'type':'string'}}}}}}}
        for key,child in list(item.items()):
            if key!='result_answer':schema(child)
    elif isinstance(item,list):
        for child in item:schema(child)
    return item


def catalog(session):
    rows=[]
    for oid,obs in session.observation_records.items():
        if not obs.get('capture_verified'):continue
        state=load_json(obs['evidence']['state']['path'])
        for node in state.get('elements',[]):
            quote=node.get('text') or ''
            if node.get('visible') is not True or not substantive_result_text(quote,numeric=False):continue
            execution=result_execution_binding(session,oid,state,node)
            if not execution:continue
            identity={'observation_id':oid,'node':node['element_id'],'quote':quote}
            rows.append({'evidence_id':'result-'+object_sha256(identity)[:16],**identity,
                'url':state['url'],'document_identity':state.get('document_identity'),
                'image':obs['evidence']['image'],'state':obs['evidence']['state'],
                'bbox':node.get('bbox'),'source':'host_synchronized_rendered_node',
                'result_execution_binding':execution})
    return rows


def answer_rows(session,plan,decision=None, *, page_binding=None):
    ref=decision or getattr(session,'result_completion',None)
    if not ref:return None
    if not enabled(session.task):raise ValueError('RESULT_COMPLETION_PROTOCOL_NOT_FROZEN')
    verify_evidence([ref]);event=load_json(ref['path'])
    reply=event.get('response',{})
    if (event.get('kind')!='plan-branch' or reply.get('choice')!='finish_result'
            or not any(o.get('choice')=='finish_result' for o in event.get('options',[]))):
        raise ValueError('RESULT_COMPLETION_NOT_OFFERED')
    if getattr(session,'attempt_id',reply.get('attempt_id'))!=reply.get('attempt_id'):
        raise ValueError('RESULT_COMPLETION_WRONG_ATTEMPT')
    answers=(reply.get('result_answer') or {}).get('check_answers',[])
    indices=[a.get('check_index') for a in answers]
    if sorted(indices)!=list(range(len(plan.get('checks',[])))):
        raise ValueError('RESULT_COMPLETION_REQUIRES_EVERY_ORIGINAL_CHECK_ONCE')
    sources={r['evidence_id']:r for r in catalog(session)};rows=[]
    for answer in sorted(answers,key=lambda a:a['check_index']):
        check=plan['checks'][answer['check_index']];proofs=[]
        for identity in answer.get('evidence_ids',[]):
            if identity not in sources:raise ValueError('RESULT_COMPLETION_UNKNOWN_SOURCE: '+str(identity))
            proof=deepcopy(sources[identity]);quote=proof['quote']
            if page_binding:
                from .plan_evidence import page_matches
                bound=page_binding['resolved_pages'][answer['check_index']]
                state=load_json(proof['state']['path'])
                if not bound or not page_matches(bound,state):
                    raise ValueError('RESULT_COMPLETION_WRONG_ORIGINAL_PAGE')
            if not substantive_result_text(quote,field=check.get('field',''),numeric=False):
                raise ValueError('RESULT_COMPLETION_LABEL_IS_NOT_ANSWER')
            expected=check.get('visible_text')
            if expected and expected not in quote and not match_result(expected,quote,
                    field=check.get('field',''),result_bound=True):
                raise ValueError('RESULT_COMPLETION_CONFLICTS_WITH_ORIGINAL_CHECK')
            if process_field(check.get('field','')) and not process_result_text(quote,check.get('field','')):
                raise ValueError('RESULT_COMPLETION_PROCESS_NOT_SHOWN')
            proofs.append(proof)
        if not proofs:raise ValueError('RESULT_COMPLETION_MISSING_ACTUAL_OUTPUT')
        rows.append({**check,'status':'VERIFIED','evidence':proofs,'seen_outside_allowed_source':[],
                     'observed_visible_text':'；'.join(p['quote'] for p in proofs),
                     'completion_mapping':'agent_original_check_to_submitted_result'})
    return rows
