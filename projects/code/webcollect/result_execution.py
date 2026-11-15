"""Deterministic result and page feedback from already captured observations.

A visible carrier is never sufficient: this attempt's real input or submission
must establish the result's cause. No answer is calculated.
"""
import re
from .batch_core import load_json
from .plan_protocol import RESULT_EXECUTION_POLICY

VERSION = RESULT_EXECUTION_POLICY
RESULT_REGIONS = ('结果区','结果区域','计算结果','计算结果/正文','计算结果/业务区域','IRS计算器结果区')
_ESCAPE = re.compile(r'\\u[0-9a-fA-F]{4}')
_SUBMIT = re.compile(r'计算|計算|提交|生成|转换|轉換|换算|換算|求解|搜索|calculate|compute|submit|convert|solve|search', re.I)


def page_feedback(state, *, scope=None):
    elements={e['element_id']:e for e in state.get('elements',[])}
    bindings={b['element_id']:b for b in state.get('capture_controls',[])}
    invalid=[]; unreadable=[]
    for cid,e in elements.items():
        if e.get('visible') is not True:continue
        if scope is not None:
            from .screenshot_effect import business_scope
            if business_scope(state, cid) != scope:
                continue
        b=bindings.get(cid,{})
        role=e.get('native_role');text=e.get('visible_text', e.get('text')) or ''
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


def frozen_input_refs(session, oid, form, *, verify_input=None):
    """A real submission may use a frozen, visible default without a fake edit.

    verify_input lets a 策略 2 template pass its own input verifier; the default
    keeps the historical monolith implementation for existing callers.
    """
    from copy import copy
    if verify_input is None:
        from .screenshot_plan import _verify_input as verify_input
    from .screenshot_effect import business_scope
    before = _state(session, oid)
    if not before or not form:
        return []
    prefix = copy(session)
    ids = list(session.observation_records)
    prefix.observation_records = {key: session.observation_records[key] for key in ids[:ids.index(oid) + 1]}
    output = []
    for requirement in getattr(session, 'requirements', []):
        if requirement.get('kind') != 'input':
            continue
        # Here we prove the actual state at submission, not historical completion.
        expected = {**requirement, 'evidence_scope': 'current'}
        answer = {'evidence': [{'observation': oid, 'control': cid} for cid in session.observation_records[oid]['controls']]}
        check, _ = verify_input(prefix, answer, expected, trusted_capture=True)
        if not check:
            continue
        proof = check['evidence'][0]
        if business_scope(before, proof['node']) != form:
            continue
        output.append({'operation_id': None, 'node': proof['node'], 'form_selector': form,
            'after_observation_id': oid, 'input_origin': 'frozen_visible_state',
            'requirement_id': requirement['id'], 'captured_input': proof})
    return output


def visible_control_texts(state, node):
    """Painted native display value only; option inventory is not visible text."""
    if node.get('visible') is not True:
        return []
    value = next((v for v in state.get('values', []) if v.get('element_id') == node.get('element_id')), {})
    selected = node.get('native_role') == 'select' or _binding(state, node.get('element_id')).get('tag') == 'select'
    text = value.get('display_value') if selected else value.get('value')
    return [text] if value.get('value_visible') is True and isinstance(text, str) and text.strip() else []


def visible_result_texts(state, node):
    """Captured visible carriers only; editable controls use values, never labels."""
    if node.get('visible') is not True:
        return []
    cid = node['element_id']
    binding = _binding(state, cid)
    if node.get('inputable') or node.get('native_role') in ('input', 'textarea', 'select') or binding.get('tag') in ('input', 'textarea', 'select'):
        return visible_control_texts(state, node)
    texts = [str(node.get('visible_text') if 'visible_text' in node else node.get('text') or '').strip()]
    flat = lambda value: re.sub(r'\s+', '', str(value or ''))
    for block in state.get('text_blocks', []):
        if block.get('element_id') != cid:
            continue
        visible = str(block.get('visible_text') or '')
        for text in [visible, *(block.get('complete_sentences') or [])]:
            if text and flat(text) in flat(visible) and flat(text) in flat(state.get('visible_text')):
                texts.append(str(text).strip())
    return list(dict.fromkeys(text for text in texts if text))


def _changed_result_binding(s, oid, state, node):
    """Prove output update from another input, with actual edit/submit mechanism."""
    from .screenshot_effect import business_scope, input_edit_row, input_facts
    texts = visible_result_texts(state, node)
    scope = business_scope(state, node['element_id'])
    if not texts or not scope:
        return None
    if any(page_feedback(state, scope=scope)[key] for key in ('validation_feedback', 'unreadable_critical_ui')):
        return None
    def identity(captured, cid):
        binding = _binding(captured, cid)
        if not binding.get('selector') or not binding.get('tag'):
            return None
        return (captured.get('document_identity'), cid, binding['selector'],
                binding['tag'], binding.get('index', 0), business_scope(captured, cid))
    result_identity = identity(state, node['element_id'])
    if result_identity is None:
        return None
    order = {key: i for i, key in enumerate(s.observation_records)}
    inputs = []
    output = None
    for row in _rows(s):
        if order.get(row.get('after_observation_id'), 10**9) > order.get(oid, -1):
            continue
        before = _state(s, row.get('before_observation_id'))
        after = _state(s, row.get('after_observation_id'))
        if not before or not after or before.get('document_identity') != state.get('document_identity') or after.get('document_identity') != state.get('document_identity'):
            continue
        cid = (row.get('target') or {}).get('control_id')
        if business_scope(before, cid) != scope:
            continue
        edit = input_edit_row(s, row)
        submit = submission_row(row, before)
        if not edit and not submit:
            continue
        output = None  # Any newer relevant input/submission invalidates the old result.
        if edit:
            inputs.append({'operation_id': row.get('operation_id'), 'node': cid,
                'form_selector': scope, 'after_observation_id': row['after_observation_id']})
        matching = [r for r in inputs if r['node'] != node['element_id']]
        if submit and not matching:
            matching = [r for r in frozen_input_refs(s, row['before_observation_id'], scope) if r['node'] != node['element_id']]
        if not matching or cid == node['element_id']:
            continue
        old_node = next((e for e in before.get('elements', []) if e['element_id'] == node['element_id']), {})
        new_node = next((e for e in after.get('elements', []) if e['element_id'] == node['element_id']), {})
        if (identity(after, node['element_id']) != result_identity
                or old_node and identity(before, node['element_id']) != result_identity):
            continue
        old = visible_result_texts(before, old_node) if old_node else []
        new = visible_result_texts(after, new_node) if new_node else []
        if new != texts or new == old:
            continue
        source_values = {str(f.get('value')) for key, f in input_facts(after).items()
                         if key in {r['node'] for r in matching}}
        if any(text in source_values for text in texts):
            continue  # A copied input is not evidence of conversion.
        feedback = page_feedback(after, scope=scope)
        if feedback['validation_feedback'] or feedback['unreadable_critical_ui']:
            continue
        output = {'policy': RESULT_EXECUTION_POLICY, 'result_region_selector': _binding(state, node['element_id']).get('result_region_selector'),
            'result_node': node['element_id'], 'result_observation_id': oid,
            'mechanism': 'submit' if submit else 'edit', 'result_value_change_required': True,
            'submission': {'operation_id': row.get('operation_id'), 'node': cid,
                'before_observation_id': row['before_observation_id'], 'after_observation_id': row['after_observation_id'],
                'scope': scope, 'input_refs': matching}, 'additional_model_calls': 0}
    return output


def result_execution_binding(s, oid, state, node, *, explicit_submission=None):
    """Bind a real result node to this attempt's input and submit, not a table.

    explicit_submission lets a 策略 2 template pass its own predicate; the
    default keeps the historical monolith implementation for existing callers.
    """
    changed = _changed_result_binding(s, oid, state, node)
    if changed:
        required = explicit_submission
        if required is None:
            from .screenshot_plan import explicit_submission_required as required
        if changed.get('mechanism') != 'edit' or not required(s):
            return changed
    binding=_binding(state,node['element_id'])
    if (not binding.get('result_region_selector') or node.get('inputable')
            or node.get('native_role') in ('input','select','textarea','h1','h2','h3','label','button')):return None
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
        if is_submit and not matching and screenshot:
            matching = frozen_input_refs(s, row['before_observation_id'], form)
        current_feedback = page_feedback(state, scope=form)
        after_feedback = page_feedback(after, scope=form)
        if (is_submit and matching and not current_feedback['validation_feedback']
                and not current_feedback['unreadable_critical_ui']
                and not after_feedback['validation_feedback'] and not after_feedback['unreadable_critical_ui']):
            # The result must already be captured after submission. Scrolling
            # to a previously unseen static tax table cannot establish causality.
            result_selector=binding['result_region_selector']
            after_bindings={b['element_id']:b for b in after.get('capture_controls',[])}
            after_results=[e for e in after.get('elements',[]) if e.get('visible') is True
                and after_bindings.get(e['element_id'],{}).get('result_region_selector')==result_selector
                and (e.get('visible_text', e.get('text')) or '')==(node.get('visible_text', node.get('text')) or '')]
            if not after_results:continue
            selector=binding.get('selector','')
            if re.search(r'(?:^| > )table:',selector):
                before_bindings={b['element_id']:b for b in before.get('capture_controls',[])}
                old=[e.get('visible_text', e.get('text')) for e in before.get('elements',[])
                    if before_bindings.get(e['element_id'],{}).get('result_region_selector')==result_selector]
                if (node.get('visible_text', node.get('text')) or '') in old:continue
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
            'input_operation_ids':[r['operation_id'] for r in execution['submission']['input_refs'] if r.get('operation_id')]})
    if not rows:return None
    final_result='；'.join((str(r['field'])+'：' if r['field'] else '')+r['visible_result'] for r in rows)
    return {'policy':RESULT_EXECUTION_POLICY,'final_result':final_result,
            'completion_judgement':'本次操作结果已核验；各事项由所列原观察中的实际结果支持：'+final_result+'。',
            'basis':rows,'is_ai_review':False}
