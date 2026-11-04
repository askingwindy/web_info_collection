"""Derive actual interaction families and customer tags from executed evidence.

Planning intent, site categories, URLs/titles containing brand/product/game words
are never a substitute for an actual control transition or a reading action.
"""
import re
ENUM = ['搜索查询','填写表单','修改设置','创建/编辑/保存文件','发送消息','预约日程','购买流程',
        '筛选排序','上传下载','导入导出','权限配置','内容发布','数据查看','问题排查']
VERSION = 'webcollect-actual-task-types-2'


def classify(record):
    from .batch_core import load_json
    rows=record['trajectory']; evidence=[]; families=[]; tags=[]
    states={oid:load_json(o['state_path']) for oid,o in record['observations'].items()}
    final_id=record['terminal'].get('final_observation_id') or (rows[-1]['after_observation_id'] if rows else None)
    final=states.get(final_id,{})
    query_controls=set(); inputs=[]; calculations=[]; reading=[]; unsupported=[]

    def add(family,tag,row,basis,**extra):
        families.append(family)
        if tag:tags.append(tag)
        evidence.append({'interaction_type':family,'customer_tag':tag,'operation_id':row['operation_id'],
            'before_observation_id':row['before_observation_id'],'after_observation_id':row['after_observation_id'],
            'basis':basis,**extra})

    def has(pattern,text):return bool(re.search(pattern,text,re.I))
    for row in rows:
        before=states[row['before_observation_id']];after=states[row['after_observation_id']]
        action=row['action'];target=row.get('target') or {};cid=target.get('control_id')
        e=next((e for e in before.get('elements',[]) if e['element_id']==cid),{})
        binding=next((c for c in before.get('capture_controls',[]) if c['element_id']==cid),{})
        # The saved label is from the real pre-dispatch label proof, not goal/
        # expected prose or the model's first-round intention.
        label=target.get('label') or e.get('text','')
        old=next((v for v in before.get('values',[]) if v.get('element_id')==cid),{})
        new=next((v for v in after.get('values',[]) if v.get('element_id')==cid),{})
        fields=(row.get('effect_evidence') or {}).get('fields',[])
        control_changed=any(x in fields for x in ('target.value','target.checked','target.selected'))
        control_changed=control_changed or any(old.get(k)!=new.get(k) for k in ('value','checked','selected','selection'))
        if 'target.owner.state' in fields:
            from .react_protocol import control_state_transition
            transition=control_state_transition(before,after,cid)
            control_changed=control_changed or bool(transition and transition['state'] in ('selected','checked','unchecked'))
        result_changed=(before.get('url')!=after.get('url') or 'visible_content' in fields or
                        before.get('visible_text')!=after.get('visible_text'))
        rendered_result=bool((after.get('visible_text') or '').strip()) and result_changed
        is_query=binding.get('input_type')=='search' or has(r'搜索|检索|查找|搜尋|search|query',label)
        if is_query and cid:query_controls.add(cid)
        if action=='type' and (control_changed or before.get('values')!=after.get('values')):
            inputs.append(row)
            add('query_input' if is_query else 'form_input','填写表单',row,'Actual input changed observed values.',target_label=label)
        execute_query=(action in ('click','double_click') and has(r'搜索|检索|查询|查找|搜尋|search',label)) or (
            action=='hotkey' and any(str(k).casefold() in ('enter','return') for k in row.get('arguments',{}).get('keys',[])) and cid in query_controls)
        if execute_query and rendered_result:
            add('search_query','搜索查询',row,'Actual query submission followed by changed rendered results/navigation.',target_label=label)
        filter_label=has(r'筛选|篩選|排序|升序|降序|从低到高|从高到低|sort|filter',label)
        if action in ('select','click','double_click','hotkey') and filter_label and rendered_result:
            add('filter_sort','筛选排序',row,'Actual filter/sort control followed by changed rendered content.',target_label=label)
        setting_label=has(r'主题|主題|深色|浅色|暗色|字[体體号號]|语言|語言|显示设置|顯示設定|设置|設定|theme|font|language|settings',label)
        if action in ('select','click','double_click','hotkey') and setting_label and control_changed:
            add('settings_change','修改设置',row,'Rendered settings label and actual control-state transition.',target_label=label)
        if action in ('click','double_click') and has(r'计算|計算|换算|換算|转换|轉換|calculate|convert',label):
            calculations.append(row)
        board=(e.get('native_role') in ('canvas','iframe','frame','object','embed') or e.get('element_type') in ('canvas','window'))
        if board and action in ('click','double_click','drag','hotkey','type'):
            # An opaque surface does not establish a played game, nor does it
            # fit a customer enum merely because other text is visible.
            unsupported.append(row)
            add('opaque_surface_interaction',None,row,'Actual interaction on a self-painting/opaque surface; gameplay semantics remain unverified.',target_role=e.get('native_role'))
        elif action=='scroll' and before.get('scroll')!=after.get('scroll') and (after.get('visible_text') or '').strip():
            reading.append(row)
        elif action in ('click','double_click','open_url','back') and before.get('url')!=after.get('url') and (after.get('visible_text') or '').strip():
            reading.append(row)
        # Purchase requires an executed explicit transaction-stage control and
        # a changed, visible cart/checkout result. A product page/book excerpt
        # or a merchant's main category does not grant this tag.
        if action in ('click','double_click') and has(r'加入购物车|加入購物車|立即购买|立即購買|去结算|去結算|提交订单|提交訂單|add to cart|checkout',label) and rendered_result and has(r'购物车|購物車|结算|結算|订单|訂單|cart|checkout',after.get('visible_text','')):
            add('purchase_stage','购买流程',row,'Actual purchase-stage control and changed visible transaction result; no completed purchase inferred.',target_label=label)

    if calculations and inputs and (final.get('visible_text') or '').strip():
        initial=states[rows[0]['before_observation_id']].get('visible_text','')
        novel=[line for line in final.get('visible_text','').splitlines() if line.strip() and line not in initial]
        if any(re.search(r'\d',line) for line in novel):
            add('tool_calculation','数据查看',calculations[-1],'Actual form inputs and calculation control; new numeric result visible in the final frame.',final_observation_id=final_id,result_excerpt='\n'.join(novel)[:300])
    # Directed reading is based on actual navigation/scroll plus rendered text,
    # including game rules and merchant-hosted excerpts. No title deny-list.
    if reading:
        for row in reading:
            add('directed_reading','数据查看',row,'Actual navigation/scroll exposed rendered content.',final_observation_id=final_id)
    from .consumer_page_policy import enabled as page_policy, ending_evidence
    if page_policy(record['task']) and ending_evidence(record['task'],rows,states,final_id):
        add('access_boundary_return','问题排查',rows[-1],
            'Observed login/download boundary, then actually cancelled/returned. No login or file transfer completed.')
    if not families and rows and (final.get('visible_text') or '').strip() and not unsupported:
        # A focus-only action does not prove a completed data-viewing task.
        families.append('unclassified_control_interaction')
    order=['搜索查询','筛选排序','修改设置','购买流程','填写表单','数据查看','问题排查']
    unique=set(tags);tags=[tag for tag in order if tag in unique][:3]
    return {'rule_version':'webcollect-actual-task-types-3-boundary-return' if page_policy(record['task']) else VERSION,'status':'DERIVED' if tags else 'REVIEW_REQUIRED',
            'interaction_types':list(dict.fromkeys(families)),'task_type':tags,'evidence':evidence,
            'planning_intents':record['terminal'].get('planning_intents',[]),
            'reason':None if tags else 'Actual interaction has no proven customer enum; preserve its internal type and evidence for review.'}
