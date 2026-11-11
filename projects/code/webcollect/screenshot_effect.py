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



def input_facts(state):
    """Known input facts, keyed by source identity; absence is never an empty value."""
    elements = {e['element_id']: e for e in state.get('elements', [])}
    bindings = {b['element_id']: b for b in state.get('capture_controls', [])}
    facts = {}
    for value in state.get('values', []):
        cid = value['element_id']; element = elements.get(cid, {}); binding = bindings.get(cid, {})
        if not (element.get('inputable') or binding.get('tag') in ('input', 'select', 'textarea')
                or element.get('native_role') in ('input', 'select', 'textarea', 'checkbox', 'radio', 'combobox')):
            continue
        row = {key: value[key] for key in ('value', 'checked', 'focused', 'selection_start',
               'selection_end', 'all_text_selected', 'input_type', 'value_visible') if key in value and value[key] is not None}
        row.update({key: element[key] for key in ('enabled', 'state') if key in element})
        row['identity'] = [state.get('document_identity'), cid, binding.get('selector'), binding.get('tag')]
        facts[cid] = row
    return facts


def input_changes(before, after, cid=None):
    old, new = input_facts(before), input_facts(after)
    if before.get('document_identity') != after.get('document_identity'):
        return []
    changes = []
    for key in ([cid] if cid else old):
        if key not in old or key not in new or old[key]['identity'] != new[key]['identity']:
            continue
        for field in ('value', 'checked'):
            if field in old[key] and field in new[key] and old[key][field] != new[key][field]:
                changes.append({'control': key, 'field': field, 'before': old[key][field], 'after': new[key][field]})
    return changes


def business_scope(state, cid):
    """Use a real form, otherwise the nearest captured business container."""
    bindings = {b['element_id']: b for b in state.get('capture_controls', [])}
    elements = {e['element_id']: e for e in state.get('elements', [])}
    binding = bindings.get(cid, {})
    if binding.get('form_selector'):
        return ['form', binding['form_selector']]
    # Snapshot selectors preserve a concrete business wrapper even when only
    # interactive nodes and main were captured (the Muxtly calculator).
    parts = (binding.get('selector') or '').split(' > ')
    for index, part in enumerate(parts[:-2]):
        if part.split(':')[0] in ('main', 'article', 'section', 'form'):
            child = parts[index + 1].split(':')[0]
            if child in ('div', 'section', 'form', 'article'):
                return ['container', ' > '.join(parts[:index + 2])]
    cursor = elements.get(cid, {}).get('parent_id'); seen = set()
    while cursor in elements and cursor not in seen:
        seen.add(cursor); element = elements[cursor]; b = bindings.get(cursor, {})
        if (element.get('native_role') in ('form', 'section', 'region', 'article', 'dialog')
                and b.get('selector')):
            return ['container', b['selector']]
        cursor = element.get('parent_id')
    return None


def input_edit_row(session, row):
    """Strategy 2 edits are captured state transitions, including deletion keys."""
    from .batch_core import load_json
    if row.get('definite_zero_effect'):
        return False
    states = []
    for key in ('before_observation_id', 'after_observation_id'):
        observation = session.observation_records.get(row.get(key))
        if not observation or not observation.get('capture_verified'):
            return False
        states.append(load_json(observation['evidence']['state']['path']))
    return bool(input_changes(*states, (row.get('target') or {}).get('control_id')))


def step_expectation(step, state, cid):
    if step.get('action') not in ('type', 'select'):
        return None
    fact = input_facts(state).get(cid, {})
    actual = fact.get('value')
    return {'expected_value': step.get('expected_value'), 'actual_value': actual,
            'matched': 'expected_value' in step and actual is not None
                       and str(actual) == str(step['expected_value']), 'control': cid}
