"""Evidence-only reading position; seen means displayed, never human comprehension."""
from .planning import object_sha256

VERSION = 'webcollect-reading-progress-1'
END_POLICY = 'webcollect-five-effective-visible-ending-1'


def lines(state):
    return list(dict.fromkeys(s.strip() for s in (state.get('visible_text') or '').splitlines() if s.strip()))


def same_view(before, after):
    return all(before.get(k) == after.get(k) for k in ('url','scroll','values','elements','visible_text'))


def control_return(origin, middle, returned, next_operation):
    """A reverse scroll may restore an offscreen control for the next real act.

    No prose-only waiver: the next dispatched action must use the same visible
    labeled control, absent from the intermediate viewport, on the same page.
    """
    if next_operation.get('action_type') not in ('click','double_click','type','select','hotkey'):
        return False
    cid=(next_operation.get('evidence') or {}).get('anchor_element_id')
    if not cid or not same_view(origin,returned) or origin.get('url') != middle.get('url'):
        return False
    def shown(state):
        width,height=state.get('screen_resolution',[0,0])
        return [e for e in state.get('elements',[]) if e.get('element_id') == cid
                and e.get('visible') is True and (e.get('text') or '').strip()
                and len(e.get('bbox',[]))==4
                and 0 <= e['bbox'][0] < e['bbox'][2] <= width
                and 0 <= e['bbox'][1] < e['bbox'][3] <= height]
    old=shown(origin);new=shown(returned)
    return bool(len(old)==len(new)==1 and not shown(middle)
                and old[0].get('text')==new[0].get('text')
                and new[0]['text']==next_operation.get('evidence',{}).get('target_label'))


def project(observations, current_id, trajectory):
    current = observations[current_id]; state = current.get('state', current)
    # Callers supply chronological accepted observations, including inspect-only
    # observations. A link label is not evidence of having visited its content.
    seen = set(); earlier = []
    for oid, item in observations.items():
        if oid == current_id: break
        old = item.get('state', item)
        text = lines(old)
        if old.get('url') == state.get('url'):
            seen.update(text)
            earlier.append({'observation_id':oid,'scroll':old.get('scroll'),
                            'text_sha256':object_sha256(text), 'visible_quotes':text[:3]})
    text = lines(state); new = [line for line in text if line not in seen]
    repeat = any(same_view(state, item.get('state', item)) for oid,item in observations.items() if oid != current_id)
    return {'schema_version':VERSION,'observation_id':current_id,'url':state.get('url'),
            'position':state.get('scroll'), 'displayed_line_count':len(text),
            'new_line_count':len(new),'already_displayed_line_count':len(text)-len(new),
            'new_visible_quotes':new[:5], 'previous_positions':earlier[-6:],
            'exact_view_seen_before':repeat,
            'last_actions':[{'action':r['action'],'arguments':r.get('arguments'),
                            'goal':r.get('semantic_goal') or r.get('goal')} for r in trajectory[-4:]],
            'meaning':'displayed_only_not_read_or_goal_completed',
            'instruction':'继续阅读先核对new_visible_quotes和位置；已有目标的可见事实已齐且有效操作≥5就立即finish。回看须指出原观察与待核对的具体文字，不能只为凑步。原样两步往返仍拒绝；导航返回可用于有据的另一分支。'}


def ending(effective, state):
    return {'schema_version':END_POLICY,'effective_operations':effective,
            'finish_complete_counted':False,'wait_counted':False,
            'minimum_reached':effective>=5,'visible_terminal_material':bool(lines(state)),
            'goal_completion':'NOT_CLAIMED','automatic_success':False,
            'instruction':'5个真实有效操作且目标可见结果已齐就立即finish；第五步本身不证明成功。未到5步自然完成按short_flow单列；没有可见终态不得声明完成。'}
