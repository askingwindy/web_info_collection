"""Deterministic result and page feedback from already captured observations.

A semantic result container is necessary, but never sufficient: an input and
submission from this attempt must precede the result. No answer is calculated.
"""
import re
from .batch_core import load_json
from .plan_protocol import RESULT_EXECUTION_POLICY

VERSION = RESULT_EXECUTION_POLICY
RESULT_REGIONS = ('结果区','结果区域','计算结果','计算结果/正文','计算结果/业务区域','IRS计算器结果区')
_ESCAPE = re.compile(r'\\u[0-9a-fA-F]{4}')
_SUBMIT = re.compile(r'计算|計算|提交|生成|转换|轉換|换算|換算|求解|搜索|calculate|compute|submit|convert|solve|search', re.I)


def page_feedback(state):
    elements={e['element_id']:e for e in state.get('elements',[])}
    bindings={b['element_id']:b for b in state.get('capture_controls',[])}
    invalid=[]; unreadable=[]
    for cid,e in elements.items():
        if e.get('visible') is not True:continue
        b=bindings.get(cid,{})
        role=e.get('native_role');text=e.get('text') or ''
        if b.get('validation_message') or b.get('aria_invalid')=='true':
            invalid.append({'node':cid,'message':b.get('validation_message') or text,'aria_invalid':b.get('aria_invalid')})
        elif b.get('aria_role')=='alert' and re.search(r'无效|無效|错误|錯誤|请输入|請輸入|必须|必須|invalid|required|error',text,re.I):
            invalid.append({'node':cid,'message':text})
        # Literal escapes in code/pre paragraphs are ordinary technical content.
        if (e.get('clickable') or e.get('inputable') or role in ('button','label','option','select','input','textarea')
                or b.get('result_region_selector')) and _ESCAPE.search(text):
            unreadable.append({'node':cid,'visible_text':text,'reason':'LITERAL_UNICODE_ESCAPE_IN_CRITICAL_UI'})
    return {'policy':RESULT_EXECUTION_POLICY,'validation_feedback':invalid,'unreadable_critical_ui':unreadable,
            'business_submission_accepted':False if invalid else None,
            'additional_model_calls':0}


def _state(s, oid):
    obs=s.observation_records.get(oid)
    return load_json(obs['evidence']['state']['path']) if obs and obs.get('capture_verified') else None


def _binding(state,cid):
    return next((b for b in state.get('capture_controls',[]) if b['element_id']==cid),{})


def _rows(s):
    rows=list(s.trajectory)
    known={r.get('operation_id') for r in rows}
    # A synchronized, definite zero-effect submit can yield the same number.
    # Retain its dispatch as evidence without granting an effective action.
    for ref in getattr(s,'business_attempt_refs',[]):
        for raw_ref in load_json(ref['path']).get('raw_steps',[]):
            raw=load_json(raw_ref['path']);react=raw.get('react',{});op=raw.get('operation',{})
            if (op.get('operation_id') not in known and raw.get('dispatched') is True
                    and raw.get('action_executed') is True and not raw.get('unknown') and not react.get('unknown')
                    and react.get('zero_effect') is True and react.get('after_observation_id')):
                rows.append({'operation_id':op.get('operation_id'),'action':op.get('action_type'),
                    'arguments':op.get('arguments',{}),'target':{'control_id':op.get('evidence',{}).get('anchor_element_id')},
                    'before_observation_id':react.get('before_observation_id'),
                    'after_observation_id':react['after_observation_id'],'definite_zero_effect':True})
    order={oid:i for i,oid in enumerate(s.observation_records)}
    return sorted(rows,key=lambda r:order.get(r.get('after_observation_id'),-1))


def is_submission(action, arguments, binding, element):
    """One submit predicate for dispatch guards and completion evidence.

    Focusing an input is never a submission. A native submit control, an
    explicitly labelled submit action, or Enter may be one. An arbitrary
    type=button control (expand/cancel/etc.) is not inherently a submission.
    """
    if action == 'hotkey':
        return 'enter' in str((arguments or {}).get('keys', arguments or {})).lower()
    if action != 'click':
        return False
    input_type = (binding or {}).get('input_type')
    label = (element or {}).get('text') or ''
    return bool(input_type == 'submit' or _SUBMIT.search(label))


def submission_row(row, before_state):
    """Return the real submit identity of a trajectory row, if it has one."""
    cid = (row.get('target') or {}).get('control_id')
    binding = _binding(before_state, cid)
    element = next((e for e in before_state.get('elements', []) if e['element_id'] == cid), {})
    return is_submission(row.get('action'), row.get('arguments'), binding, element)


def result_execution_binding(s, oid, state, node):
    """Bind a real result node to this attempt's input and submit, not a table."""
    binding=_binding(state,node['element_id'])
    if (not binding.get('result_region_selector') or node.get('inputable')
            or node.get('native_role') in ('input','select','textarea','h1','h2','h3','label','button')
            or page_feedback(state)['validation_feedback'] or page_feedback(state)['unreadable_critical_ui']):return None
    order={key:i for i,key in enumerate(s.observation_records)}
    inputs=[];submit=None
    from .collection_strategy import enabled
    screenshot = enabled(s.task)
    from .screenshot_effect import business_scope, input_edit_row
    for row in _rows(s):
        if order.get(row.get('after_observation_id'),10**9)>order.get(oid,-1):continue
        before=_state(s,row.get('before_observation_id'));after=_state(s,row.get('after_observation_id'))
        if not before or not after or after.get('document_identity')!=state.get('document_identity'):continue
        if row.get('effective') is not True and not row.get('effect_evidence',{}).get('verified') and not row.get('definite_zero_effect'):continue
        cid=(row.get('target') or {}).get('control_id');b=_binding(before,cid)
        e=next((e for e in before.get('elements',[]) if e['element_id']==cid),{})
        action=row.get('action');form=business_scope(before, cid) if screenshot else b.get('form_selector')
        if (input_edit_row(s, row) if screenshot else action in ('type','select') and not row.get('definite_zero_effect')):
            inputs.append({'operation_id':row['operation_id'],'node':cid,'form_selector':form,
                           'after_observation_id':row['after_observation_id'],'arguments':row.get('arguments')})
            if not screenshot or submit is None or submit.get('scope') == form:
                submit=None
        is_submit = is_submission(action, row.get('arguments'), b, e)
        matching=[i for i in inputs if form and i['form_selector']==form] if screenshot else [i for i in inputs if not form or i['form_selector']==form]
        if is_submit and matching and not page_feedback(after)['validation_feedback']:
            # The result must already be captured after submission. Scrolling
            # to a previously unseen static tax table cannot establish causality.
            result_selector=binding['result_region_selector']
            after_bindings={b['element_id']:b for b in after.get('capture_controls',[])}
            after_results=[e for e in after.get('elements',[]) if e.get('visible') is True
                and after_bindings.get(e['element_id'],{}).get('result_region_selector')==result_selector
                and (e.get('text') or '')==(node.get('text') or '')]
            if not after_results:continue
            selector=binding.get('selector','')
            if re.search(r'(?:^| > )table:',selector):
                before_bindings={b['element_id']:b for b in before.get('capture_controls',[])}
                old=[e.get('text') for e in before.get('elements',[])
                    if before_bindings.get(e['element_id'],{}).get('result_region_selector')==result_selector]
                if (node.get('text') or '') in old:continue
            result_form=business_scope(state, node['element_id']) if screenshot else binding.get('form_selector')
            if result_form and form!=result_form:continue
            submit={'operation_id':row['operation_id'],'before_observation_id':row['before_observation_id'],
                    'after_observation_id':row['after_observation_id'],'node':cid,
                    'definite_zero_effect':row.get('definite_zero_effect',False),'input_refs':matching,
                    **({'scope': form} if screenshot else {})}
    if not submit:return None
    return {'policy':RESULT_EXECUTION_POLICY,'result_region_selector':binding['result_region_selector'],
            'result_node':node['element_id'],'result_observation_id':oid,'submission':submit,
            'result_value_change_required':False,'additional_model_calls':0}


def completion_result_summary(evidence, *, final_observation_id):
    """Client-facing facts from the actual captured result observations.

    Preserve prior source IDs rather than claiming every answer is in the last frame.
    This is an annotation basis, not an independent review or status override.
    """
    if evidence.get('business_goal_status')!='VERIFIED':return None
    rows=[]
    for check in evidence.get('checks',[]):
        if check.get('status')!='VERIFIED':return None
        proofs=[p for p in check.get('evidence',[]) if p.get('result_execution_binding')]
        if not proofs:continue
        quotes={p.get('quote') for p in proofs if p.get('quote')}
        if len(quotes)!=1:return None
        proof=proofs[0];execution=proof['result_execution_binding']
        rows.append({'field':check.get('field'),'visible_result':proof['quote'],
            'observation_id':proof['observation_id'],'node':proof['node'],'url':proof['url'],
            'submission_operation_id':execution['submission']['operation_id'],
            'input_operation_ids':[r['operation_id'] for r in execution['submission']['input_refs']]})
    if not rows:return None
    final_result='；'.join((str(r['field'])+'：' if r['field'] else '')+r['visible_result'] for r in rows)
    return {'policy':RESULT_EXECUTION_POLICY,'final_result':final_result,
            'completion_judgement':'本次输入已提交；各事项由所列原观察中的实际结果支持：'+final_result+'。',
            'basis':rows,'is_ai_review':False}
