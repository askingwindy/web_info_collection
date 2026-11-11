"""策略 2 native target binding and step compilation.

Native copies of the semantic-target binding rules (verbatim from the frozen
conditional-plan implementation, including its 2026-11 provenance comments)
so 策略 2 sessions never import the 策略 1 controller module banded_plan.
Behavior stays byte-identical; 策略 2-specific tuning happens here only.
"""
from copy import deepcopy

from .batch_core import load_json

# 2026-11-07 wwiki A/B: models describe controls with standard ARIA role words
# (textbox/searchbox/link) while the host records native tag roles (input/a).
# The two vocabularies name the same control kind; equivalence is not a
# loosening of uniqueness -- every other declared field still has to match.
ROLE_EQUIVALENTS = {'textbox': ('input', 'textarea'), 'searchbox': ('input',),
                    'combobox': ('input', 'select'), 'link': ('a',), 'button': ('button',),
                    'image': ('img',), 'heading': ('h1', 'h2', 'h3', 'h4', 'h5', 'h6'),
                    'checkbox': ('input',), 'radio': ('input',), 'listbox': ('select',),
                    'spinbutton': ('input',)}


def roles_equivalent(declared, native):
    if not declared:
        return True
    return declared == native or native in ROLE_EQUIVALENTS.get(str(declared).strip().lower(), ())


def execution_keys(keys,platform=None):
    import sys
    aliases={'control':'ctrl','command':'meta','cmd':'meta'}
    result=[aliases.get(k.lower(),k.lower()) for k in keys]
    return ['meta','a'] if result==['ctrl','a'] and (platform or sys.platform)=='darwin' else result


def _identity_only_binding(control, semantic):
    """A unique current node reference with href/visibility evidence binds when
    no visible text exists to contradict the declared label.

    Real ambiguity is not guessed: any visible label that disagrees with the
    declaration, or a declared href/role that differs, still fails binding.
    """
    element = control.get('element', {})
    labels = [r['text'] for r in control.get('readable_labels', [])]
    text = semantic.get('text') or ''
    if element.get('visible') is not True:
        return False
    if any(label or element.get('text') for label in labels + [element.get('text', '')]):
        return text in labels + [element.get('text', '')]
    href = semantic.get('href')
    if href and control.get('binding', {}).get('href') != href:
        return False
    role = semantic.get('role')
    if role and not roles_equivalent(role, element.get('native_role')):
        return False
    return True


def bind_target(observation, target, observations=None, *, carriers=True, advisory=False):
    # A short node reference is evidence from one archived observation. It may
    # survive a same-document probe only with unchanged node identity/binding.
    reference=None
    identity_bound=False
    if target.get('node'):
        original=(observations or {}).get(target.get('observation_id'))
        if target.get('observation_id')==observation['observation_id']:original=observation
        if not original or original['document_identity']!=observation['document_identity']:return []
        reference=original['controls'].get(target['node'])
        current=observation['controls'].get(target['node'])
        if not reference or not current:return []
        semantic={k:v for k,v in target.items() if k not in ('node','observation_id')}
        if advisory:
            semantic = advisory_target(original, target, semantic)
        if target['node'] not in bind_target(original,semantic,carriers=False):
            # The 2026-11-06 loops: a uniquely identified visible node (icon
            # link, image link with no rendered text) plus its href is binding
            # evidence even when the page exposes no text for it.
            if not _identity_only_binding(current, semantic):return []
            identity_bound=True
        if any(reference.get('binding',{}).get(k)!=current.get('binding',{}).get(k) for k in ('selector','href')):return []
    if advisory and reference is not None:
        target = {**target, **semantic}
        for key in ('parent_text', 'region'):
            if key not in semantic: target.pop(key, None)
    controls=observation['controls']; elements={r['element_id']:r for r in
        load_json(observation['evidence']['state']['path']).get('elements',[])}
    state=load_json(observation['evidence']['state']['path'])
    from .plan_evidence import region_matches
    def semantic_matches(semantic):
        rows=[]
        for cid,c in controls.items():
            if reference is not None and cid!=semantic.get('node',target.get('node')):continue
            e=c['element']; labels=[r['text'] for r in c.get('readable_labels',[])]
            if e.get('visible') is not True:continue
            if identity_bound:
                # A visible label that disagrees with the declaration is a conflict.
                if (labels or e.get('text')) and semantic['text'] not in labels+[e.get('text','')]:continue
            elif semantic['text'] not in labels+[e.get('text','')]:continue
            if semantic.get('role') and not roles_equivalent(semantic['role'],e.get('native_role')):continue
            if semantic.get('href') and c.get('binding',{}).get('href')!=semantic['href']:continue
            if semantic.get('region') and not region_matches(state,cid,semantic['region']):continue
            if semantic.get('parent_text'):
                parent=elements.get(e.get('parent_id'),{})
                if semantic['parent_text']!=parent.get('text'):continue
            rows.append(cid)
        return rows
    matches=semantic_matches(target)
    if (not matches and advisory and reference is None
            and target.get('text') and (not target.get('region')
                or not __import__('re').search(r'左|右|\bleft\b|\bright\b',target['region'],__import__('re').I))):
        # 2026-11-07 wwiki-B: an over-specific semantic declaration (unproved
        # region prose, a sibling's parent_text) must not veto a step whose base
        # identity (text+role+href) binds exactly one visible current control.
        # Directional region declarations stay hard, mirroring advisory_target.
        base={k:v for k,v in target.items() if k not in ('parent_text','region','region_hint')}
        unique=semantic_matches(base)
        if len(unique)==1:matches=unique
    if not carriers:return matches
    resolved=[]
    for cid in matches:
        node=elements.get(cid,{})
        seen=set()
        while node.get('native_role') not in ('a','button','input','textarea','select') and node.get('parent_id') not in seen:
            parent=elements.get(node.get('parent_id'),{})
            if not parent or parent.get('visible') is not True:break
            seen.add(node.get('parent_id'));node=parent
            if node.get('native_role') in ('a','button','input','textarea','select') and node.get('clickable'):
                cid=node['element_id'];break
        if cid not in resolved:resolved.append(cid)
    return resolved


def advisory_target(observation, target, semantic):
    """Additional prose cannot veto a uniquely proved current node and label.

    A node is not an ambiguity resolver: same-name controls, explicit side
    constraints, href/role and advertising ancestry remain mandatory.
    """
    import re
    from .plan_evidence import region_matches
    state=load_json(observation['evidence']['state']['path'])
    cid=target['node']; control=observation['controls'].get(cid,{})
    element=control.get('element',{}); binding=control.get('binding',{})
    if (not observation.get('capture_verified') or element.get('visible') is not True
            or not any(v.get('status')=='PROVEN' or v.get('reason')=='MISSING_TARGET_PROBE' for v in control.get('actions',{}).values())):
        return semantic
    basic={k:v for k,v in semantic.items() if k not in ('parent_text','region','region_hint')}
    if bind_target(observation,basic,carriers=False) != [cid]: return semantic
    selector=binding.get('selector','')
    if re.search(r'(?:advert|sponsor|(?:^|[\s>:.#_-])ads?(?:[\s>:.#_-]|$))',selector,re.I):
        return semantic
    result=deepcopy(semantic)
    region=result.get('region','')
    # Directional declarations are always hard, even when supplied as prose.
    directional=bool(re.search(r'左|右|\bleft\b|\bright\b',region,re.I))
    if region and not directional and not region_matches(state,cid,region):
        result.pop('region')
    result.pop('parent_text',None)
    return result



def react_step(step, control_ids, endpoint_matches):
    """Compile one planned screenshot step into a native act() step.

    rationale stays the model's own independent field (never a purpose alias)
    and expected keeps the explicit pre-execution expectation; neither
    degenerates to an action or control name. The compiled step is what the
    engine validates and dispatches atomically.
    """
    action = step['action']
    actual = {'action': action, 'goal': step.get('purpose') or action,
              'expected': step.get('expected_result'),
              'rationale': step.get('rationale'), 'expected_result': step.get('expected_result')}
    for key in ('value', 'keys', 'direction', 'page_id', 'duration_ms'):
        if key in step:
            actual[key] = step[key]
    if action == 'hotkey' and isinstance(actual.get('keys'), list):
        actual['keys'] = execution_keys(actual['keys'])
    if action in ('click', 'double_click', 'right_click', 'drag', 'type', 'select'):
        actual['control_id'] = control_ids[0]
    if action == 'hotkey':
        actual['control_id'] = control_ids[0] if control_ids else None
    if action == 'drag':
        matches = endpoint_matches(step.get('end_target') or {}) or []
        if len(matches) != 1:
            raise ValueError('DRAG_DESTINATION_NOT_UNIQUELY_BOUND')
        actual['end_control_id'] = matches[0]
    return actual
