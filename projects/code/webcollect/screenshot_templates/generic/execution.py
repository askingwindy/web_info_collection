"""策略 2 · generic 模板 native target binding and step compilation (独立模板包拷贝)。

Native copies of the semantic-target binding rules (verbatim from the frozen
conditional-plan implementation, including its 2026-11 provenance comments)
so 策略 2 sessions never import the 策略 1 controller module banded_plan.
Behavior stays byte-identical; 策略 2-specific tuning happens here only.
"""
from copy import deepcopy

from webcollect.batch_core import load_json

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


def control_carrier(state, cid):
    """Nearest captured native action owner, preserving the real child target."""
    elements = {row['element_id']: row for row in state.get('elements', [])}
    bindings = {row['element_id']: row for row in state.get('capture_controls', [])}
    def native(node):
        return (bindings.get(node.get('element_id'), {}).get('tag') in ('a', 'button', 'input', 'textarea', 'select')
                or node.get('native_role') in ('a', 'button', 'input', 'textarea', 'select'))
    node = elements.get(cid, {})
    seen = set()
    while not native(node):
        parent_id = node.get('parent_id')
        if not parent_id or parent_id in seen:
            break
        seen.add(parent_id)
        parent = elements.get(parent_id, {})
        if not parent or parent.get('visible') is not True:
            break
        node = parent
        if native(node) and node.get('clickable'):
            return node['element_id']
    return cid


def navigation_carrier(state, cid):
    """Captured link provenance for either a link or its real clicked child."""
    owner = control_carrier(state, cid)
    element = next((row for row in state.get('elements', []) if row['element_id'] == owner), {})
    binding = next((row for row in state.get('capture_controls', []) if row['element_id'] == owner), {})
    if (element.get('visible') is not True
            or not element.get('clickable') or binding.get('tag') != 'a' or not binding.get('href')):
        return None
    return {'target_node': cid, 'link_node': owner, 'selector': binding.get('selector'),
            'index': binding.get('index', 0), 'href': binding['href'], 'target': binding.get('target')}


def bind_target(observation, target, observations=None, *, carriers=True, advisory=False):
    if target.get('_source'):
        return resolve_control(observation, target)
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
    from webcollect.plan_evidence import region_matches
    def semantic_matches(semantic):
        rows=[]
        for cid,c in controls.items():
            if reference is not None and cid!=semantic.get('node',target.get('node')):continue
            e=c['element']; labels=[r['text'] for r in c.get('readable_labels',[])]
            if e.get('visible') is not True:continue
            # A target may legally declare no text (a region-only scroll target),
            # so absence means no text constraint, mirroring role/href/region below.
            declared=semantic.get('text')
            if declared is not None:
                if identity_bound:
                    # A visible label that disagrees with the declaration is a conflict.
                    if (labels or e.get('text')) and declared not in labels+[e.get('text','')]:continue
                elif declared not in labels+[e.get('text','')]:continue
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
        cid = control_carrier(state, cid)
        if cid not in resolved:resolved.append(cid)
    return resolved


def advisory_target(observation, target, semantic):
    """Additional prose cannot veto a uniquely proved current node and label.

    A node is not an ambiguity resolver: same-name controls, explicit side
    constraints, href/role and advertising ancestry remain mandatory.
    """
    import re
    from webcollect.plan_evidence import region_matches
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
    for key in ('value', 'expected_value', 'keys', 'direction', 'page_id', 'duration_ms'):
        if key in step:
            actual[key] = step[key]
    if action == 'hotkey' and isinstance(actual.get('keys'), list):
        actual['keys'] = execution_keys(actual['keys'])
    if action in ('click', 'double_click', 'right_click', 'drag', 'type', 'select'):
        actual['control_id'] = control_ids[0]
    if action == 'scroll' and step.get('target'):
        if not control_ids or len(control_ids) != 1:
            raise ValueError('SCROLL_CONTAINER_NOT_UNIQUELY_BOUND')
        actual['control_id'] = control_ids[0]
    if action == 'hotkey':
        actual['control_id'] = control_ids[0] if control_ids else None
    if action == 'drag':
        matches = endpoint_matches(step.get('end_target') or {}) or []
        if len(matches) != 1:
            raise ValueError('DRAG_DESTINATION_NOT_UNIQUELY_BOUND')
        actual['end_control_id'] = matches[0]
    return actual



def validate_input_precondition(step, value, probe=None):
    """Check observed insertion facts; never synthesize focus/select/clear.

    Number editors may not expose selection offsets. Unknown selection remains
    unknown and the post-action expected_value receipt verifies the real result.
    A click or double click never manufactures full selection here.
    """
    if step.get('action') != 'type':
        return
    if (probe or {}).get('focused') is not True and value.get('focused') is not True:
        raise ValueError('TYPE_REQUIRES_CURRENT_FOCUS: explicitly focus the field first')
    current = value.get('value')
    if not isinstance(current, str):
        raise ValueError('MISSING_INPUT_STATE')
    start, end = value.get('selection_start'), value.get('selection_end')
    encoded = current.encode('utf-16-le', errors='surrogatepass')
    if value.get('all_text_selected') is True:
        predicted = step['value']
    elif (type(start) is int and type(end) is int
          and 0 <= start <= end <= len(encoded) // 2):
        predicted = (encoded[:start * 2] + step['value'].encode('utf-16-le', errors='surrogatepass')
                     + encoded[end * 2:]).decode('utf-16-le', errors='surrogatepass')
    elif not current:
        predicted = step['value']
    elif (value.get('input_type') == 'number' and value.get('all_text_selected') is False
          and step.get('expected_value') == step['value']):
        raise ValueError('TYPE_REPLACEMENT_REQUIRES_OBSERVED_SELECTION_OR_EMPTY_VALUE: '
                         'double_click does not prove full selection; explicitly select/delete then observe')
    else:
        return
    if predicted != step.get('expected_value'):
        raise ValueError('TYPE_INSERTION_EXPECTATION_MISMATCH: current value and selection would produce '
                         + repr(predicted) + '; explicitly select/delete, observe the empty value, then type')


def compile_step(task, page_urls, step, observation, navigation_count=0):
    """Compile exactly one declared atomic action; never synthesize focus/clear."""
    action = step['action']
    if action not in task['fragment']['allowed_actions'] or action == 'set_value':
        raise ValueError('ACTION_NOT_PUBLISHED_FOR_SCREENSHOT_STRATEGY')
    if action in ('type', 'select') and ('expected_value' not in step or not isinstance(step['expected_value'], str)):
        raise ValueError('EXPECTED_VALUE_REQUIRED: declare the final input value')
    cid = step.get('control_id')
    control = observation['controls'].get(cid)
    if action == 'scroll' and cid:
        container = (control or {}).get('binding', {}).get('scroll_container') or {}
        axis = 'y' if step.get('direction') in ('up', 'down') else 'x'
        if (not control or control.get('element', {}).get('visible') is not True
                or not container.get('visible') or axis not in container.get('axes', [])):
            raise ValueError('SCROLL_CONTAINER_NOT_CURRENTLY_SCROLLABLE')
    if action in ('click', 'double_click', 'right_click', 'type', 'select', 'drag'):
        if not control:
            raise ValueError('TARGET_NOT_CURRENTLY_OBSERVED')
        truth = control.get('actions', {}).get(action, {})
        if truth.get('status') != 'PROVEN':
            raise ValueError(truth.get('status', 'INSUFFICIENT') + ': ' + truth.get('reason', 'MISSING_TARGET_PROBE'))
    keys = execution_keys(step.get('keys', [])) if action == 'hotkey' else []
    if action == 'hotkey' and not cid and (keys in (['meta', 'a'], ['ctrl', 'a'])
            or any(key in ('backspace', 'delete') for key in keys)):
        raise ValueError('HOTKEY_REQUIRES_CURRENT_TARGET_FOCUS: bind the input target before editing keys')
    if action == 'hotkey' and cid:
        # Ordinary post-click captures carry actual focus in values/elements;
        # a target probe is obtained again by the dispatch guard before keys.
        focused = (((control or {}).get('probe') or {}).get('focused') is True
                   or ((control or {}).get('value') or {}).get('focused') is True
                   or ((control or {}).get('element') or {}).get('focused') is True
                   or ((control or {}).get('element') or {}).get('state') == 'focused')
        if not focused:
            raise ValueError('HOTKEY_REQUIRES_CURRENT_TARGET_FOCUS')
    if action == 'back' and navigation_count < 1:
        raise ValueError('NO_SESSION_NAVIGATION_TO_RETURN_FROM')
    if action == 'open_url':
        page = step.get('page_id', '')
        if not page.startswith('p') or not page[1:].isdigit() or int(page[1:]) >= len(page_urls):
            raise ValueError('NAVIGATION_REQUIRES_OBSERVED_PAGE')
    row = deepcopy(step)
    if action == 'type':
        value = control.get('value') or {}
        validate_input_precondition(step, value, control.get('probe'))
        if (value.get('input_type') == 'number' and value.get('value')
                and value.get('focused') is True and value.get('all_text_selected') is True
                and (control.get('probe') or {}).get('focused') is True):
            # This is already observed selection, not a synthesized clear/focus.
            row['replace_selected_number'] = value['value']
    if action == 'select':
        options = control['binding'].get('options', [])
        matches = [o for o in options if str(o.get('value')) == str(step.get('value')) and not o.get('disabled')]
        if len(matches) != 1 or sum(o.get('label') == matches[0].get('label') for o in options) != 1:
            raise ValueError('SELECT_OPTION_NOT_PROVEN: use one unique enabled option value from current options')
        if str(step['value']) == str(control.get('value', {}).get('value')):
            raise ValueError('UNCHANGED_SELECTION')
        row['option'] = matches[0]['label']
    if action == 'drag':
        endpoint = observation['controls'].get(step.get('end_control_id')) or {}
        if not endpoint.get('element', {}).get('visible') or step.get('end_control_id') == cid:
            raise ValueError('DRAG_DESTINATION_NOT_UNIQUELY_BOUND')
    return [row]


def _source(observation, cid, mark_number=None):
    c = observation['controls'][cid]
    return {'observation_id': observation['observation_id'], 'document_identity': observation['document_identity'],
            'control_id': cid, 'binding': {k: c.get('binding', {}).get(k) for k in ('selector', 'index', 'tag', 'href')},
            'labels': [r.get('text') for r in c.get('readable_labels', []) if r.get('kind') not in ('visible_native_value', 'visible_selected_option')],
            'text': c.get('element', {}).get('text', ''), 'role': c.get('element', {}).get('native_role'),
            **({'mark_number': mark_number} if mark_number is not None else {})}


def cited_control(observation, cited, allowed):
    """Resolve one cited mark to a control of the current frame.

    The marked viewport labels each provided control with its 1-based position
    in provided_control_ids, so the number the model sees on the image names
    exactly one control; the projected id is accepted as the same citation.
    Anything else stays a refusal rather than a fuzzy guess.
    """
    direct = cited if cited in allowed and cited in observation['controls'] else None
    # Use only the number map projected from this exact observation. Never
    # infer an ordinal from a later frame or from dictionary ordering.
    numbered = (observation.get('provided_control_numbers') or {}).get(cited)
    if numbered not in allowed or numbered not in observation['controls']:
        numbered = None
    if direct and numbered and direct != numbered:
        raise ValueError('CONTROL_NUMBER_CONFLICT: ' + str(cited))
    if direct or numbered:
        return direct or numbered, int(cited) if numbered else None
    return None, None


def _normalize_node_target(target, observation, allowed, normalization):
    node = target.get('node')
    if not node:
        return
    cid, mark = cited_control(observation, node, allowed)
    controls = observation.get('controls', {})
    if cid is None:
        # Prose is a determinate alias only when one current rendered control
        # matches its actual label and every explicit role/href constraint.
        from .plan import _flat
        matches = []
        for key in allowed:
            c = controls.get(key, {}); e = c.get('element', {})
            if e.get('visible') is not True or not roles_equivalent(target.get('role'), e.get('native_role')):
                continue
            if target.get('href') and c.get('binding', {}).get('href') != target['href']:
                continue
            labels = [r['text'] for r in c.get('readable_labels', [])
                      if r.get('kind') != 'visible_native_value']
            if e.get('text') and not e.get('inputable'):
                labels.append(e['text'])
            if target.get('text') and target['text'] not in labels + [e.get('text')]:
                continue
            role_alias = node in ('input', 'select', 'textarea', 'button', 'a') and roles_equivalent(node, e.get('native_role'))
            if role_alias or any(len(_flat(label)) >= 2 and _flat(label) in _flat(node) for label in labels):
                matches.append(key)
        cid = matches[0] if len(matches) == 1 else None
    if cid is None:
        candidates = [{'control': key, 'text': controls[key].get('element', {}).get('text'),
                       'labels': [r['text'] for r in controls[key].get('readable_labels', [])]}
                      for key in sorted(allowed) if key in controls]
        from webcollect import workspace_json as json
        raise ValueError('TARGET_NODE_NOT_UNIQUELY_BOUND: node='+repr(node)+
            '; use text for a rendered label or control for its current ID; current candidates='+
            json.dumps(candidates, ensure_ascii=False))
    if target.get('control'):
        explicit, _ = cited_control(observation, target['control'], allowed)
        if explicit != cid:
            raise ValueError('CONTROL_TARGET_CONFLICT: node and control identify different current controls')
    target.pop('node')
    target.setdefault('control', cid)
    normalization.append({'field': 'target.node', 'original': node, 'control': cid,
                          'observation': observation['observation_id'], 'transform': 'unique_current_control_alias'})


def bind_plan_targets(plan, observation, allowed_ids=None, *, normalization=None):
    """Bind the current segment; future documents retain declared semantics."""
    from urllib.parse import urldefrag, urljoin
    allowed = set(allowed_ids if allowed_ids is not None else observation.get('provided_control_ids', []))
    normalization = normalization if normalization is not None else []
    steps = plan.get('steps', [])
    future = False
    for index, step in enumerate([*steps, *[r for r in plan.get('requirements', []) if r.get('kind') == 'input' or r.get('result_kind') == 'input_conversion']]):
        deferred = future and index < len(steps)
        for key in ('target', 'end_target'):
            target = step.get(key) or {}
            if deferred:
                # Never reinterpret a first-frame number as a new-page control.
                # An explicitly declared semantic target may be rebound when
                # that page is actually observed; no unseen labels are invented.
                if (target.get('control') or target.get('node')) and not any(
                        target.get(field) for field in ('text', 'href', 'region')):
                    raise ValueError('FUTURE_TARGET_REQUIRES_SEMANTICS: use text/role/href, not a current control number')
                if target.get('control') or target.get('node') or target.get('_source'):
                    target.pop('control', None); target.pop('node', None); target.pop('_source', None)
                    normalization.append({'field': f'steps[{index}].{key}',
                                          'transform': 'future_target_keeps_declared_semantics'})
                continue
            _normalize_node_target(target, observation, allowed, normalization)
            cited = target.get('control')
            mark = None
            if cited:
                cid, mark = cited_control(observation, cited, allowed)
                if cid is None:
                    raise ValueError('CONTROL_NOT_PROVIDED_TO_MODEL: ' + str(cited))
                control = observation['controls'][cid]
                element = control.get('element') or {}
                labels = [r['text'] for r in control.get('readable_labels', [])]
                if (target.get('role') and not roles_equivalent(target['role'], element.get('native_role'))
                        or target.get('text') and target['text'] not in labels + [element.get('text', '')]
                        or target.get('href') and target['href'] != control.get('binding', {}).get('href')):
                    raise ValueError('CONTROL_TARGET_CONFLICT: ' + str(cited))
                target['control'] = cid
            elif target.get('text'):
                matches = bind_target(observation, target)
                cid = matches[0] if len(matches) == 1 and matches[0] in allowed else None
            else:
                cid = None
            if cid:
                target['_source'] = _source(observation, cid, mark)
        if index < len(steps):
            target = step.get('target') or {}
            href = target.get('href') or target.get('_source', {}).get('binding', {}).get('href')
            navigation = (step.get('action') in ('back', 'open_url') or
                (step.get('action') in ('click', 'double_click') and href and
                 urldefrag(urljoin(observation.get('url', ''), href))[0] !=
                 urldefrag(observation.get('url', ''))[0]))
            future = future or bool(navigation)
    return plan


def resolve_control(observation, target):
    """Old numeric ids cannot silently select a new node after rerender."""
    source = target.get('_source')
    if not source or source['document_identity'] != observation['document_identity']:
        return []
    def matches(cid):
        current = _source(observation, cid)
        return (observation['controls'][cid].get('element', {}).get('visible') is True
                and all(current[k] == source[k] for k in ('binding', 'text', 'role'))
                and (not source['labels'] or current['labels'] == source['labels']))
    cid = source['control_id']
    if cid in observation['controls'] and matches(cid):
        return [cid]
    # A rerender may issue new ids. Exact selector, href, role and rendered
    # labels must identify one current control; no fuzzy label matching.
    candidates = [cid for cid in observation['controls'] if matches(cid)]
    return candidates if len(candidates) == 1 else []
