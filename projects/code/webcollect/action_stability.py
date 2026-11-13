"""Action-scoped dispatch and observation evidence.

Every ordinary action proves only the action-relevant minimum: the dispatched
target's identity/visibility/hit/occlusion (click), focus and value
(type/hotkey on the unique focused control) or the document basis
(scroll/back/open_url). Unrelated suggestion popups, announcements, SVG and
repaints may change freely. Post-dispatch effects keep the per-action
predicates in react_protocol/goal_evidence. Full originals stay intact.
"""
from copy import deepcopy
from io import BytesIO
import hashlib
from PIL import Image, ImageChops

from .plan_protocol import ACTION_STABILITY_PROTOCOL

VERSION = ACTION_STABILITY_PROTOCOL


ACTION_SCOPED_VERSION = ACTION_STABILITY_PROTOCOL
ACTION_SCOPED_VERSIONS = (ACTION_SCOPED_VERSION,)
VERSIONS = ACTION_SCOPED_VERSIONS
CLICK_POINT_VERSION = 'click-dispatch-point'
BACK_OBSERVED_VERSION = 'back-observed-document'


def action_scoped_projection(state, node, action, *, click_validation=None):
    """Target-level identity proof: unique node, visible/enabled, in-viewport
    box, loaded readiness and hit/obstruction samples; focus+value for inputs.
    Volatile unrelated DOM (suggestions, announcements) never enters it."""
    def unique(rows):
        found = [r for r in rows if r.get('element_id') == node]
        if len(found) != 1:
            raise ValueError('Action-scoped target is missing or ambiguous')
        return found[0]
    element = unique(state.get('elements', []))
    binding = unique(state.get('capture_controls', []))
    value = unique(state.get('values', [])) if action in ('type', 'hotkey') else None
    geometry = unique(state.get('geometry_witnesses', []))
    box = element.get('bbox') or []
    viewport = state.get('screen_resolution') or []
    readiness = state.get('capture_readiness') or {}
    samples = geometry.get('samples', [])
    geometry_ok = (len(samples) == 9 and (samples[4].get('ancestor') is True if action in ('type', 'hotkey')
                                          else all(p.get('ancestor') is True for p in samples)))
    if not element.get('visible') or not element.get('enabled') or len(box) != 4:
        raise ValueError('Action-scoped target not visible/enabled in dispatch frame')
    if (len(viewport) != 2
            or not (0 <= box[0] < box[2] <= viewport[0] and 0 <= box[1] < box[3] <= viewport[1])):
        raise ValueError('Action-scoped target outside current viewport; scroll it fully into view first')
    if (readiness.get('document_ready') != 'complete'
            or readiness.get('fonts_ready') is not True or readiness.get('images_ready') is not True):
        raise ValueError('Action-scoped dispatch frame not fully loaded')
    point_policy = action == 'click' and click_validation == CLICK_POINT_VERSION
    if click_validation is not None and not point_policy:
        raise ValueError('Unknown click validation policy')
    if not point_policy and not geometry_ok:
        raise ValueError('Action-scoped target hit samples partially obstructed or shifted; '
                         'scroll it to a fully clear position or pick another visible link')
    if action == 'click' and not element.get('clickable'):
        raise ValueError('Action-scoped click target is not clickable')
    if action in ('type', 'hotkey'):
        native_textarea = element.get('native_role') == 'textarea' and binding.get('tag') == 'textarea'
        native_select_key = action == 'hotkey' and element.get('native_role') == 'select' and binding.get('tag') == 'select'
        if (not (element.get('native_role') in ('input', 'combobox') or native_textarea or native_select_key)
                or (action == 'type' and (not element.get('inputable') or value.get('readonly')))
                or not value.get('value_visible')
                or [v['element_id'] for v in state.get('values', []) if v.get('focused')] != [node]):
            raise ValueError('Action-scoped input requires an editable uniquely focused input')
    target = state.get('target')
    if target and (target.get('element_id') != node or target.get('hit_valid') is False):
        raise ValueError('Action-scoped target hit or identity changed')
    if point_policy:
        point = geometry.get('dispatch_point') or {}
        coordinate = point.get('coordinate') or []
        if (point.get('schema_version') != CLICK_POINT_VERSION or point.get('hit_valid') is not True
                or len(coordinate) != 2 or not (box[0] <= coordinate[0] < box[2]
                                                           and box[1] <= coordinate[1] < box[3])
                or target and (target.get('hit_valid') is not True or target.get('coordinate') != coordinate)):
            raise ValueError('Action-scoped actual click point is not proved on the current target')
    basis = {k: deepcopy(state.get(k)) for k in
             ('url', 'document_identity', 'scroll', 'screen_resolution', 'device_pixel_ratio')}
    basis['element'] = {k: element.get(k) for k in ('element_id', 'native_role', 'text', 'bbox',
                                                    'visible', 'enabled', 'clickable', 'inputable')}
    basis['binding'] = {k: binding.get(k) for k in ('tag', 'selector', 'index', 'href',
                                                    'input_type', 'form_index')}
    if point_policy:
        # Nine-point bounding-box probes stay in the raw snapshot as diagnostic
        # evidence. Actual clickability follows the exact dispatched point and
        # the existing rendered-label/pixel proof, never an ancestor edge hit.
        basis['dispatch_point'] = deepcopy(point)
    else:
        basis['geometry'] = {k: deepcopy(geometry[k]) for k in
                             ('schema_version', 'rendered_bbox', 'samples') if k in geometry}
    if action in ('type', 'hotkey'):
        basis['value'] = {k: value.get(k) for k in ('focused', 'value', 'readonly', 'value_visible')}
    return basis


def action_scoped_scope(state, node, action, *, version=ACTION_SCOPED_VERSION):
    if version not in ACTION_SCOPED_VERSIONS:
        raise ValueError('Unknown action-scoped policy')
    if action not in ('click', 'type', 'hotkey') or not node:
        raise ValueError('Action-scoped node proof supports click/type/hotkey on a target')
    from .dynamic_regions import projection as content_projection
    projected = content_projection(state, protect=[node])
    geometry = next((g for g in projected.get('geometry_witnesses', []) if g.get('element_id') == node), {})
    validation = CLICK_POINT_VERSION if action == 'click' and (
        geometry.get('dispatch_point') or {}).get('schema_version') == CLICK_POINT_VERSION else None
    return {'schema_version': version, 'action': action,
            'purpose': 'action_scoped_dispatch', 'node': node,
            **({'click_validation': validation} if validation else {}),
            'basis': action_scoped_projection(projected, node, action, click_validation=validation)}


def document_scope(state, action, *, version=ACTION_SCOPED_VERSION):
    """Document basis for target-less actions: identity (and pre-scroll
    position) stable during the capture; unrelated pixels may repaint."""
    if version not in ACTION_SCOPED_VERSIONS:
        raise ValueError('Unknown action-scoped policy')
    if action not in ('scroll', 'back', 'open_url', 'hotkey'):
        raise ValueError('Document scope supports scroll/back/open_url/hotkey')
    readiness = state.get('capture_readiness') or {}
    observed_back = action == 'back'
    if observed_back and (not state.get('url') or not state.get('document_identity')):
        raise ValueError('Back requires the observed document URL and identity')
    if readiness.get('document_ready') not in ('interactive', 'complete'):
        raise ValueError('Document scope requires a loaded document')
    keys = ('url', 'document_identity', 'scroll') if action == 'scroll' else ('url', 'document_identity')
    return {'schema_version': version, 'action': action,
            'purpose': 'document_scoped_dispatch', 'node': None,
            'readiness_policy': 'document-observed',
            'basis': {k: deepcopy(state.get(k)) for k in keys}}


def post_action_document_scope(source, operation=None, *, version=ACTION_SCOPED_VERSION):
    """Post-dispatch observation proof: the captured document is internally
    settled (same url+identity across the capture triple). Observation only;
    the action effect itself is verified by the per-action predicates."""
    if version not in ACTION_SCOPED_VERSIONS:
        raise ValueError('Unknown action-scoped policy')
    return {'schema_version': version, 'action': 'observe',
            'purpose': 'post_action_document',
            **({'operation_id': operation['operation_id']} if operation else {}),
            'source_url': source.get('url'), 'allow_navigation': True}


def action_scoped_view_stable(before, after):
    """Action-scoped ending-view comparison: same document and scroll with the
    visible reading material retained. Unrelated decorative image/overlay
    membership changes and repaints are not endpoint changes; projected text
    equality keeps the read content honest."""
    if not isinstance(before, dict) or not isinstance(after, dict):
        return False
    for key in ('document_identity', 'scroll'):
        if before.get(key) != after.get(key):
            return False
    from .dynamic_regions import projection
    def visible_texts(state):
        projected = projection(state)
        return {row.get('text') for row in projected.get('elements', [])
                if row.get('visible') and row.get('text')}
    return visible_texts(before) == visible_texts(after)


def _observation_layout(state):
    """Visible business layout, excluding classified motion and empty decoration.

    Incidental hit-test ancestry on an untargeted box is not visible content.
    Its raw witnesses remain in the receipt; target evidence stays complete.
    """
    from .dynamic_regions import projection
    projected = projection(state)
    target_id = (projected.get('target') or {}).get('element_id')
    business = [row for row in projected.get('elements', [])
                if row.get('text') or row.get('clickable') or row.get('inputable')
                or row.get('element_id') == target_id]
    keys = ('element_id', 'element_type', 'native_role', 'text', 'bbox',
            'clickable', 'inputable', 'visible', 'enabled', 'state')
    ids = {row.get('element_id') for row in business}
    return {
        **{key: projected.get(key) for key in
           ('scroll', 'screen_resolution', 'visible_text', 'values', 'target')},
        'business_elements': [{key: row.get(key) for key in keys} for row in business],
        'business_geometry': [{key: row.get(key) for key in
                               ('element_id', 'bbox', 'rendered_bbox')}
                              for row in projected.get('geometry_witnesses', [])
                              if row.get('element_id') in ids],
    }


def _action_scoped_pair(before, after, png_before, png_after, scope):
    from .browser import fingerprint
    action = scope.get('action')
    purpose = scope.get('purpose')
    version = scope['schema_version']
    observation_only = purpose in ('post_action_document', 'entry_observation')
    with Image.open(BytesIO(png_before)) as a, Image.open(BytesIO(png_after)) as b:
        if a.format != 'PNG' or b.format != 'PNG' or a.size != b.size or list(a.size) != before['screen_resolution']:
            raise ValueError('Action-scoped proof needs complete original viewport PNGs')
        guard = local = None
        if purpose == 'action_scoped_dispatch' and action in ('click', 'type', 'hotkey') and scope.get('node'):
            box = scope['basis']['element']['bbox']
            guard = [max(0, box[0] - 4), max(0, box[1] - 4), min(a.width, box[2] + 4), min(a.height, box[3] + 4)]
        if guard is not None:
            # Keep the full originals and their hashes; only the comparison
            # uses the already-required target box plus its four-pixel margin.
            channels = ImageChops.difference(a.crop(tuple(guard)).convert('RGBA'),
                                             b.crop(tuple(guard)).convert('RGBA')).split()
            diff = channels[0]
            for channel in channels[1:]:
                diff = ImageChops.lighter(diff, channel)
            local = diff.point(lambda x: 255 if x else 0).histogram()[255]
            pixels = {'comparison': 'target_region', 'protected_changed_pixels': local,
                      'protected_bbox': guard}
        else:
            # Decode to retain the original complete-PNG integrity check.
            # Document-only evidence never claims an unchecked image is equal.
            a.load(); b.load()
            pixels = {'comparison': 'not_required', 'reason': 'document_identity_only'}
        valid = False
        if purpose == 'action_scoped_dispatch' and action in ('click', 'type', 'hotkey') and scope.get('node'):
            try:
                valid = (action_scoped_projection(before, scope['node'], action,
                                                  click_validation=scope.get('click_validation'))
                         == action_scoped_projection(after, scope['node'], action,
                                                      click_validation=scope.get('click_validation'))
                         == scope['basis'])
            except ValueError:
                valid = False
        elif purpose == 'document_scoped_dispatch' and action in ('scroll', 'back', 'open_url', 'hotkey'):
            observed_back = action == 'back' and scope.get('readiness_policy') == BACK_OBSERVED_VERSION
            ready_states = ('interactive', 'complete') if (observed_back or scope.get('readiness_policy') == 'document-observed') else ('complete',)
            ready = all((s.get('capture_readiness') or {}).get('document_ready') in ready_states
                        for s in (before, after))
            valid = ready and all(before.get(k) == after.get(k) == scope['basis'][k]
                                  for k in scope['basis'])
        elif observation_only:
            valid = (before.get('url') == after.get('url')
                     and before.get('document_identity') == after.get('document_identity'))
            if valid:
                # Observation-only means no dispatch permission, not permission
                # to pair an earlier layout with a later screenshot. Keep the
                # declared dynamic paint exclusions but retain business boxes,
                # hit witnesses and text across the screenshot bracket.
                valid = _observation_layout(before) == _observation_layout(after)
        else:
            raise ValueError('Unknown action-scoped proof')
        # Up to 100 changed pixels are admitted only inside the protected
        # target region; everything outside must be pixel-identical.
        tolerance = 100
        accepted = bool(valid and local <= tolerance) if local is not None else bool(valid)
    result = {'schema_version': version, 'action_scope': deepcopy(scope),
              'accepted': accepted, 'full_dom_stable': fingerprint(before) == fingerprint(after),
              'related_dom_stable': bool(valid), 'loading_complete': bool(valid),
              'before_fingerprint': fingerprint(before), 'after_fingerprint': fingerprint(after),
              'png_before_sha256': hashlib.sha256(png_before).hexdigest(),
              'png_after_sha256': hashlib.sha256(png_after).hexdigest(), 'pixel_change': pixels}
    if observation_only:
        result.update(observation_only=True, dispatch_permission=False)
    return result


def action_scoped_pair(before, after, png_before, png_after, scope):
    """Dispatcher used by browser.stability_pair and postprocess replays."""
    if scope.get('schema_version') not in ACTION_SCOPED_VERSIONS:
        raise ValueError('Unknown action-scoped policy')
    return _action_scoped_pair(before, after, png_before, png_after, scope)


def validate_dynamic_scope(before, after, scope):
    """Action-scoped scopes route to action_scoped_pair; nothing else is known."""
    if scope is None:
        return True
    raise ValueError('Unknown dynamic comparison action scope')


def reading_projection(state, node):
    mains = [e for e in state.get('elements', []) if e.get('element_id') == node
             and e.get('native_role') == 'main' and e.get('visible')]
    if len(mains) != 1:
        raise ValueError('Reading main identity changed')
    binding = next((b for b in state.get('capture_controls', []) if b['element_id'] == node), {})
    selector = binding.get('selector'); vp = state.get('screen_resolution', []); box = mains[0].get('bbox', [])
    ready = state.get('capture_readiness', {})
    if (not selector or len(vp) != 2 or len(box) != 4
            or ready.get('document_ready') != 'complete'
            or not ready.get('fonts_ready') or not ready.get('images_ready')):
        raise ValueError('Reading region not fully loaded')
    clip = [max(0, box[0]), max(0, box[1]), min(vp[0], box[2]), min(vp[1], box[3])]
    if clip[0] >= clip[2] or clip[1] >= clip[3]:
        raise ValueError('Reading region outside viewport')
    controls = [b for b in state.get('capture_controls', [])
                if b.get('selector') == selector or b.get('selector', '').startswith(selector + ' > ')]
    ids = {b['element_id'] for b in controls}
    return deepcopy({k: state.get(k) for k in
                     ('url', 'document_identity', 'scroll', 'screen_resolution', 'device_pixel_ratio', 'values')} |
                    {'element': {**mains[0], 'bbox': clip}, 'main_binding': binding, 'controls': controls,
                     'elements': [e for e in state.get('elements', []) if e['element_id'] in ids],
                     'geometry': [g for g in state.get('geometry_witnesses', []) if g['element_id'] in ids]})


def reading_scope(state):
    """Read-only document-basis proof of the rendered main region."""
    from .dynamic_regions import projection as content_projection
    state = content_projection(state)
    mains = [e for e in state.get('elements', []) if e.get('native_role') == 'main' and e.get('visible')]
    if len(mains) != 1:
        raise ValueError('Reading scroll requires one rendered main region')
    node = mains[0]['element_id']; basis = reading_projection(state, node)
    return {'schema_version': ACTION_SCOPED_VERSION, 'action': 'scroll',
            'purpose': 'observed_reading_scroll', 'node': node, 'basis': basis}


def pair(before, after, png_before, png_after, scope):
    """Entry used by read-only planning checks and postprocess replays."""
    from .dynamic_regions import enabled as dynamic_enabled, pair as dynamic_pair
    if scope.get('schema_version') in ACTION_SCOPED_VERSIONS and scope.get('purpose') != 'observed_reading_scroll':
        return action_scoped_pair(before, after, png_before, png_after, scope)
    if dynamic_enabled(before) and dynamic_enabled(after) and scope.get('purpose') != 'observed_reading_scroll':
        return dynamic_pair(before, after, png_before, png_after, action_scope=scope)
    if scope.get('purpose') == 'observed_reading_scroll':
        from .browser import fingerprint
        valid = (reading_projection(before, scope['node']) == reading_projection(after, scope['node'])
                 == scope['basis'])
        with Image.open(BytesIO(png_before)) as a, Image.open(BytesIO(png_after)) as b:
            if a.format != 'PNG' or b.format != 'PNG' or a.size != b.size or list(a.size) != before['screen_resolution']:
                raise ValueError('Reading proof needs complete original viewport PNGs')
            diff = ImageChops.difference(a.convert('RGB'), b.convert('RGB'))
            mask = ImageChops.lighter(ImageChops.lighter(*diff.split()[:2]), diff.split()[2]).point(lambda v: 255 if v else 0)
            box = scope['basis']['element']['bbox']
            guard = [max(0, box[0] - 4), max(0, box[1] - 4), min(a.width, box[2] + 4), min(a.height, box[3] + 4)]
            local = mask.crop(tuple(guard)).histogram()[255]
            pixels = {'changed_pixels': mask.histogram()[255], 'protected_changed_pixels': local,
                      'protected_bbox': guard, 'bbox': list(mask.getbbox()) if mask.getbbox() else None}
        return {'schema_version': ACTION_SCOPED_VERSION, 'action_scope': deepcopy(scope),
                'accepted': bool(valid and not local), 'full_dom_stable': fingerprint(before) == fingerprint(after),
                'related_dom_stable': valid, 'loading_complete': valid,
                'before_fingerprint': fingerprint(before), 'after_fingerprint': fingerprint(after),
                'png_before_sha256': hashlib.sha256(png_before).hexdigest(),
                'png_after_sha256': hashlib.sha256(png_after).hexdigest(), 'pixel_change': pixels}
    raise ValueError('Unknown action stability proof')
