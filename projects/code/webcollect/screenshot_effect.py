"""Strategy 2 atomic effects, shared by execution and sealed replay."""
from .plan_protocol import EFFECTIVE_ACTION_RULE

def content_effect(before, after, control_id):
    """Bind changed rendered leaves to the target branch or a result landmark.

    Geometry, accessible names, container text and unrelated sidebar refreshes
    alone cannot establish an action result. URL/value/focus have separate tests.
    """
    trees = [{e['element_id']: e for e in s.get('elements', [])} for s in (before, after)]
    def ancestors(tree, cid):
        seen = set()
        while cid in tree and cid not in seen:
            seen.add(cid)
            cid = tree[cid].get('parent_id')
        return seen
    old, new = trees
    # A bound result region is itself a result landmark: its changed leaf is
    # the submitted answer, not unrelated content refresh.
    bindings = [{b['element_id']: b for b in s.get('capture_controls', [])} for s in (before, after)]
    result_regions = {cid for group in bindings
                      for cid, b in group.items() if b.get('result_region_selector')}
    roots = set(); cursor = control_id; seen = set()
    while cursor in old and cursor not in seen:
        seen.add(cursor)
        if old[cursor].get('native_role') in ('main', 'article', 'form', 'section', 'dialog', 'alertdialog', 'region'):
            roots.add(cursor)
            break  # The nearest result scope, not every containing landmark.
        cursor = old[cursor].get('parent_id')
    if not roots:
        parent = old.get(control_id, {}).get('parent_id')
        if parent in old and old[parent].get('native_role') not in ('body', 'html'):
            roots.add(parent)
    changed = []
    for cid, e in new.items():
        chain = ancestors(new, cid)
        roles = {new[k].get('native_role') for k in chain}
        if roles & {'aside', 'complementary', 'nav', 'navigation', 'footer', 'contentinfo', 'video'}:
            continue
        text = e.get('text', '').strip()
        if not text or text not in after.get('visible_text', ''):
            continue
        if any(other.get('parent_id') == cid for other in new.values()):
            continue
        if text == old.get(cid, {}).get('text'):
            continue
        # A newly exposed dialog/list result can be mounted outside the form.
        result = any(new[k].get('native_role') in ('dialog', 'alertdialog', 'status', 'alert')
                     and (k not in old or old[k].get('text') != new[k].get('text')) for k in chain)
        if result or chain & roots or cid in result_regions or cid == control_id:
            changed.append(cid)
    return changed


def control_state_transition(before, after, control_id):
    """Follow a target's rendered owner through an exact structural rerender.

    A label match alone is insufficient. New node IDs require a unique unchanged
    selector/tag, the same document and the same visible target text. Only the
    target's own ancestor chain may supply selected/checked/expanded state.
    """
    old = {e['element_id']: e for e in before.get('elements', [])}
    new = {e['element_id']: e for e in after.get('elements', [])}
    target = old.get(control_id)
    if not target or before.get('document_identity') != after.get('document_identity'):
        return None
    bindings = [{b['element_id']: b for b in s.get('capture_controls', [])} for s in (before, after)]
    def match(cid):
        if cid in new: return cid
        binding = bindings[0].get(cid)
        if not binding: return None
        candidates = [eid for eid, b in bindings[1].items() if eid in new and
                      all(b.get(k) == binding.get(k) for k in ('selector','index','tag'))]
        return candidates[0] if len(candidates) == 1 else None
    actual = match(control_id)
    text = target.get('text', '')
    if (actual is None or not text or text != new[actual].get('text')
            or text not in before.get('visible_text','') or text not in after.get('visible_text','')):
        return None
    new_chain = set();cursor = actual
    while cursor in new and cursor not in new_chain:
        new_chain.add(cursor);cursor = new[cursor].get('parent_id')
    cursor = control_id;seen = set()
    while cursor in old and cursor not in seen:
        seen.add(cursor);owner = old[cursor];matched = match(cursor)
        if matched in new_chain and owner.get('clickable') and new[matched].get('clickable'):
            changed = new[matched].get('state')
            if (changed in ('selected','checked','unchecked','expanded','collapsed','focused')
                    and changed != owner.get('state')):
                return {'before_owner':cursor, 'after_owner':matched, 'state':changed,
                        'target_text':text, 'matched_target':actual,
                        'binding':'same_node_or_unique_selector_tag_in_same_document'}
        cursor = owner.get('parent_id')
    return None


def atomic_effect(before, after, action, arguments, control_id=None, *, rule_version=EFFECTIVE_ACTION_RULE):
    """Action-specific state evidence; a changed PNG/animation alone never counts."""
    from .dynamic_regions import projection
    before,after=projection(before,protect=[control_id]),projection(after,protect=[control_id])
    values_before = {v['element_id']: v for v in before.get('values', [])}
    values_after = {v['element_id']: v for v in after.get('values', [])}
    cid = control_id or next((cid for cid, v in values_before.items() if v.get('focused')), None)
    old, new = values_before.get(cid, {}), values_after.get(cid, {})
    fields = []
    if action == 'scroll':
        b, a = before.get('scroll'), after.get('scroll')
        direction = arguments.get('direction')
        axis = 1 if direction in ('up', 'down') else 0
        if isinstance(a, list) and isinstance(b, list) and len(a) > axis and len(b) > axis:
            delta = a[axis] - b[axis]
            if (direction in ('down', 'right') and delta > 0) or (direction in ('up', 'left') and delta < 0):
                fields.append('scroll')
    elif action in ('type', 'select'):
        if cid is not None and old.get('value') != new.get('value'):
            fields.append('target.value')
    elif action=='drag':
        before_node=next((e for e in before.get('elements',[]) if e['element_id']==cid),None)
        after_node=next((e for e in after.get('elements',[]) if e['element_id']==cid),None)
        if old.get('value')!=new.get('value'):fields.append('target.value')
        if before_node and after_node and before.get('document_identity')==after.get('document_identity'):
            if before_node.get('bbox')!=after_node.get('bbox'):fields.append('target.position')
            if before_node.get('parent_id')!=after_node.get('parent_id'):fields.append('target.parent')
            if before_node.get('state')!=after_node.get('state'):fields.append('target.state')
        if content_effect(before,after,cid):fields.append('target.content')
    elif action in ('click', 'double_click', 'right_click', 'hotkey', 'back', 'open_url'):
        if before.get('url') != after.get('url'):
            fields.append('url')
        for key in ('focused', 'checked', 'value', 'selection_start', 'selection_end'):
            if old.get(key) != new.get(key):
                fields.append('target.' + key)
        if control_state_transition(before, after, cid):
            fields.append('target.owner.state')
        if (action == 'hotkey' and arguments.get('keys') in (['meta','a'], ['ctrl','a'])
                and old.get('input_type') == new.get('input_type') == 'number'
                and old.get('focused') is True and new.get('focused') is True
                and old.get('value') and old['value'] == new.get('value')
                and old.get('all_text_selected') is False and new.get('all_text_selected') is True):
            fields.append('target.all_text_selected')
        # Rendered content transitions support menus, filtering and navigation;
        # DOM-only geometry movement and background pixels do not.
        if (before.get('visible_text') != after.get('visible_text') and before.get('elements') != after.get('elements')
                and content_effect(before, after, cid)):
            fields.append('visible_content')
    return {'verified': bool(fields), 'fields': fields, 'control_id': cid}

