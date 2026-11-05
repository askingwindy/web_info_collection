"""Explicit first-focus proof. Full originals stay intact; old rules stay strict."""
from copy import deepcopy
from io import BytesIO
import hashlib
from PIL import Image, ImageChops

VERSION = 'webcollect-first-focus-stability-1'
TYPING_VERSION = 'webcollect-search-focus-type-stability-2'
VERSIONS = (VERSION, TYPING_VERSION)


def projection(state, node, *, action='click'):
    def unique(rows):
        found = [r for r in rows if r.get('element_id') == node]
        if len(found) != 1:
            raise ValueError('Scoped target is missing or ambiguous')
        return found[0]
    element = unique(state.get('elements', []))
    binding = unique(state.get('capture_controls', []))
    value = unique(state.get('values', []))
    geometry = unique(state.get('geometry_witnesses', []))
    box = element.get('bbox') or []
    viewport = state.get('screen_resolution') or []
    readiness = state.get('capture_readiness') or {}
    roles=('input','combobox') if action=='type' else ('input',)
    samples=geometry.get('samples',[])
    geometry_ok=(len(samples)==9 and (samples[4].get('ancestor') is True if action=='type'
                                      else all(p.get('ancestor') is True for p in samples)))
    if (element.get('native_role') not in roles or (action=='type' and binding.get('tag')!='input') or not element.get('inputable')
            or not element.get('visible') or not element.get('enabled')
            or binding.get('input_type') not in ('text', 'search')
            or value.get('readonly') or len(box) != 4 or len(viewport) != 2
            or state.get('device_pixel_ratio') != 1
            or not (0 <= box[0] < box[2] <= viewport[0] and 0 <= box[1] < box[3] <= viewport[1])
            or readiness.get('document_ready') != 'complete'
            or readiness.get('fonts_ready') is not True or readiness.get('images_ready') is not True
            or not geometry_ok):
        raise ValueError('Scoped focus lacks loaded, visible, unobstructed target proof')
    target = state.get('target')
    if target and (target.get('element_id') != node or not target.get('hit_valid')
                   or not target.get('visible_label_evidence')):
        raise ValueError('Scoped target hit or readable identity changed')
    return deepcopy({k: state.get(k) for k in
        ('url', 'document_identity', 'scroll', 'screen_resolution', 'device_pixel_ratio')} | {
            'element': element, 'binding': binding, 'value': value, 'geometry': geometry})


def scope_for(state, node, selector, index=0, *, action='click', version=VERSION):
    from .dynamic_regions import projection as content_projection
    state=content_projection(state,protect=[node])
    basis = projection(state, node,action=action)
    if version not in VERSIONS or action not in ('click','type') or (action=='type' and version!=TYPING_VERSION):
        raise ValueError('Unknown scoped action policy')
    if action=='type' and not searchable(basis):
        raise ValueError('Typing scope requires a readable focused search input')
    if action=='type' and {v['element_id'] for v in state.get('values',[]) if v.get('focused')}!={node}:
        raise ValueError('Typing scope requires unique original keyboard focus')
    bindings = [r for r in state.get('capture_controls', []) if r.get('selector') == selector and r.get('index', 0) == index]
    if (len(bindings) != 1 or basis['value'].get('focused') is not (action=='type')
            or basis['binding'].get('selector') != selector or basis['binding'].get('index', 0) != index):
        raise ValueError('Scoped selector does not uniquely bind the original node')
    return {'schema_version': version, 'action': action,
            'purpose': 'focused_search_type' if action=='type' else 'first_search_focus',
            'node': node, 'selector': selector, 'index': index, 'basis': basis}


def searchable(basis):
    from .goal_evidence import norm, SEARCH_TERMS
    return (basis['value'].get('value_visible') is True and
            (basis['binding'].get('input_type')=='search' or
             any(term in norm(basis['element'].get('text') or '') for term in SEARCH_TERMS)))


def pair(before, after, png_before, png_after, scope):
    from .browser import fingerprint
    version=scope.get('schema_version');action=scope.get('action')
    if (version not in VERSIONS or
            (action,scope.get('purpose')) not in (('click','first_search_focus'),('type','focused_search_type'))
            or (action=='type' and version!=TYPING_VERSION)
            or (action=='type' and not searchable(scope['basis']))
            or scope.get('basis',{}).get('value',{}).get('focused') is not (action=='type')):
        raise ValueError('Unknown scoped action proof')
    valid = True
    try:
        left, right = projection(before, scope['node'],action=action), projection(after, scope['node'],action=action)
        valid = left == right == scope['basis']
        # Both targeted probes must retain the same hit and visible labels.
        if before.get('target') and after.get('target') and before['target'] != after['target']:
            valid = False
    except ValueError:
        valid = False
    box = scope['basis']['element']['bbox']
    with Image.open(BytesIO(png_before)) as a, Image.open(BytesIO(png_after)) as b:
        if a.format != 'PNG' or b.format != 'PNG' or a.size != b.size or list(a.size) != before['screen_resolution']:
            raise ValueError('Scoped proof needs complete original viewport PNGs')
        channels = ImageChops.difference(a.convert('RGBA'), b.convert('RGBA')).split()
        diff = channels[0]
        for channel in channels[1:]: diff = ImageChops.lighter(diff, channel)
        changed = diff.point(lambda x: 255 if x else 0)
        guard = [max(0, box[0]-4), max(0, box[1]-4), min(a.width, box[2]+4), min(a.height, box[3]+4)]
        local = changed.crop(tuple(guard)).histogram()[255]
        pixels = {'changed_pixels': changed.histogram()[255], 'bbox': list(changed.getbbox()) if changed.getbbox() else None,
                  'protected_changed_pixels': local, 'protected_bbox': guard,
                  'difference_mask_sha256': hashlib.sha256(changed.tobytes()).hexdigest()}
    return {'schema_version': version, 'action_scope': deepcopy(scope), 'accepted': bool(valid and not local),
            'full_dom_stable': fingerprint(before) == fingerprint(after), 'related_dom_stable': valid,
            'loading_complete': valid, 'before_fingerprint': fingerprint(before), 'after_fingerprint': fingerprint(after),
            'png_before_sha256': hashlib.sha256(png_before).hexdigest(), 'png_after_sha256': hashlib.sha256(png_after).hexdigest(),
            'pixel_change': pixels}

# New scope: an already observed link, or Enter on the uniquely focused search
# field. No result/scroll/terminal fact is covered by this action permission.
FOLLOWUP_VERSION = 'webcollect-search-submit-link-stability-3'
VERSIONS = (*VERSIONS, FOLLOWUP_VERSION)

def followup_projection(state,node,action):
    def one(rows):
        values=[r for r in rows if r.get('element_id')==node]
        if len(values)!=1:raise ValueError('Follow-up target missing or ambiguous')
        return values[0]
    e=one(state.get('elements',[]));b=one(state.get('capture_controls',[]));g=one(state.get('geometry_witnesses',[]))
    samples=g.get('samples',[]);box=e.get('bbox',[]);vp=state.get('screen_resolution',[])
    ready=state.get('capture_readiness',{})
    if (not e.get('visible') or not e.get('enabled') or len(samples)!=9 or not samples[4].get('ancestor')
            or len(box)!=4 or len(vp)!=2 or not (0<=box[0]<box[2]<=vp[0] and 0<=box[1]<box[3]<=vp[1])
            or ready.get('document_ready')!='complete' or not ready.get('fonts_ready') or not ready.get('images_ready')):
        raise ValueError('Follow-up target lacks visible loaded hit proof')
    if action=='click':
        if b.get('tag')!='a' or not b.get('href') or not e.get('clickable'):
            raise ValueError('Follow-up click requires a bound observed link')
    elif action=='hotkey':
        value=one(state.get('values',[]))
        if (b.get('tag')!='input' or b.get('input_type') not in ('search','text') or not value.get('focused')
                or not value.get('value_visible') or not value.get('value')
                or [v['element_id'] for v in state.get('values',[]) if v.get('focused')]!=[node]):
            raise ValueError('Submit requires unique readable focused search input')
    else:raise ValueError('Unsupported follow-up action')
    return deepcopy({k:state.get(k) for k in ('url','document_identity','scroll','screen_resolution','device_pixel_ratio','values')}|
                    {'element':e,'binding':b,'geometry':g})

def followup_scope(state,node,action):
    from .dynamic_regions import projection as content_projection
    state=content_projection(state,protect=[node])
    basis=followup_projection(state,node,action)
    return {'schema_version':FOLLOWUP_VERSION,'action':action,'purpose':'observed_search_followup','node':node,
            'selector':basis['binding']['selector'],'index':basis['binding'].get('index',0),'basis':basis}

def reading_scope(state):
    from .dynamic_regions import projection as content_projection
    state=content_projection(state)
    mains=[e for e in state.get('elements',[]) if e.get('native_role')=='main' and e.get('visible')]
    if len(mains)!=1:raise ValueError('Reading scroll requires one rendered main region')
    node=mains[0]['element_id'];basis=reading_projection(state,node)
    return {'schema_version':FOLLOWUP_VERSION,'action':'scroll','purpose':'observed_reading_scroll',
            'node':node,'basis':basis}

def reading_projection(state,node):
    mains=[e for e in state.get('elements',[]) if e.get('element_id')==node and e.get('native_role')=='main' and e.get('visible')]
    if len(mains)!=1:raise ValueError('Reading main identity changed')
    binding=next((b for b in state.get('capture_controls',[]) if b['element_id']==node),{})
    selector=binding.get('selector');vp=state.get('screen_resolution',[]);box=mains[0].get('bbox',[])
    ready=state.get('capture_readiness',{})
    if not selector or len(vp)!=2 or len(box)!=4 or ready.get('document_ready')!='complete' or not ready.get('fonts_ready') or not ready.get('images_ready'):
        raise ValueError('Reading region not fully loaded')
    clip=[max(0,box[0]),max(0,box[1]),min(vp[0],box[2]),min(vp[1],box[3])]
    if clip[0]>=clip[2] or clip[1]>=clip[3]:raise ValueError('Reading region outside viewport')
    controls=[b for b in state.get('capture_controls',[]) if b.get('selector')==selector or b.get('selector','').startswith(selector+' > ')]
    ids={b['element_id'] for b in controls}
    return deepcopy({k:state.get(k) for k in ('url','document_identity','scroll','screen_resolution','device_pixel_ratio','values')}|
                    {'element':{**mains[0],'bbox':clip},'main_binding':binding,'controls':controls,
                     'elements':[e for e in state.get('elements',[]) if e['element_id'] in ids],
                     'geometry':[g for g in state.get('geometry_witnesses',[]) if g['element_id'] in ids]})


_original_pair=pair

def pair(before,after,png_before,png_after,scope):
    if scope.get('schema_version')!=FOLLOWUP_VERSION:
        # The new task protocol retains V2 first-focus/type receipt semantics.
        return _original_pair(before,after,png_before,png_after,scope)
    from .browser import fingerprint
    if scope.get('purpose') not in ('observed_search_followup','observed_reading_scroll'):raise ValueError('Unknown follow-up proof')
    valid=False
    try:
        if scope.get('purpose')=='observed_reading_scroll':
            if scope.get('action')!='scroll':raise ValueError('Reading proof is only pre-scroll')
            valid=reading_projection(before,scope['node'])==reading_projection(after,scope['node'])==scope['basis']
        else:
            valid=followup_projection(before,scope['node'],scope['action'])==followup_projection(after,scope['node'],scope['action'])==scope['basis']
    except ValueError:pass
    with Image.open(BytesIO(png_before)) as a,Image.open(BytesIO(png_after)) as b:
        if a.format!='PNG' or b.format!='PNG' or a.size!=b.size or list(a.size)!=before['screen_resolution']:
            raise ValueError('Follow-up needs complete original PNGs')
        diff=ImageChops.difference(a.convert('RGB'),b.convert('RGB'))
        mask=ImageChops.lighter(ImageChops.lighter(*diff.split()[:2]),diff.split()[2]).point(lambda v:255 if v else 0)
        box=scope['basis']['element']['bbox'];guard=[max(0,box[0]-4),max(0,box[1]-4),min(a.width,box[2]+4),min(a.height,box[3]+4)]
        local=mask.crop(tuple(guard)).histogram()[255]
        pixels={'changed_pixels':mask.histogram()[255],'protected_changed_pixels':local,'protected_bbox':guard,'bbox':list(mask.getbbox()) if mask.getbbox() else None}
    return {'schema_version':FOLLOWUP_VERSION,'action_scope':deepcopy(scope),'accepted':bool(valid and not local),
            'full_dom_stable':fingerprint(before)==fingerprint(after),'related_dom_stable':valid,'loading_complete':valid,
            'before_fingerprint':fingerprint(before),'after_fingerprint':fingerprint(after),
            'png_before_sha256':hashlib.sha256(png_before).hexdigest(),'png_after_sha256':hashlib.sha256(png_after).hexdigest(),'pixel_change':pixels}

# Post-dispatch observations prove the new state, never permission to replay an
# operation. All snapshots and both original viewport PNGs remain in the receipt.
POST_VERSION = 'webcollect-post-action-observation-stability-4'
VERSIONS = (*VERSIONS, POST_VERSION)


def post_observation_scope(source, operation):
    action = operation.get('action_type')
    node = operation.get('evidence', {}).get('anchor_element_id') or operation.get('evidence', {}).get('focused_element_id')
    if action in ('click', 'type') and node:
        try:
            from .dynamic_regions import projection as content_projection
            basis = projection(content_projection(source,protect=[node]), node, action='type' if action=='type' else 'click')
            if searchable(basis):
                expected = operation.get('arguments', {}).get('text') if action=='type' else basis['value'].get('value')
                if isinstance(expected, str):
                    return {'schema_version':POST_VERSION,'action':'observe','purpose':'post_search_input',
                            'operation_id':operation['operation_id'],'source':basis,'expected_value':expected}
        except ValueError:
            pass
    from .dynamic_regions import enabled as dynamic_enabled,VERSION as dynamic_version
    if dynamic_enabled(source):
        return {'schema_version':POST_VERSION,'action':'observe','purpose':'shared_dynamic_regions','dynamic_protocol':dynamic_version,
            'operation_id':operation['operation_id'],'source_url':source['url'],'source_document':source['document_identity'],
            'allow_navigation':action in ('click','hotkey','back','open_url')}
    # The source must already contain a unique primary content region. The new
    # region is then proved within this capture; navigation lineage is separately
    # checked by the ordinary action/goal evidence machinery.
    reading_scope(source)
    return {'schema_version':POST_VERSION,'action':'observe','purpose':'post_primary_content',
            'operation_id':operation['operation_id'],'source_url':source['url'],
            'source_document':source['document_identity'],
            'allow_navigation':action in ('click','hotkey','back','open_url')}


_pre_post_pair = pair


def _post_pair(before, after, png_before, png_after, scope):
    if scope.get('schema_version') != POST_VERSION:
        return _pre_post_pair(before,after,png_before,png_after,scope)
    if scope.get('action')!='observe':raise ValueError('Post-action scope cannot authorize dispatch')
    if scope.get('purpose')=='post_search_input':
        source=scope['source'];label=source['element'].get('text')
        if not label or any(before.get(k)!=source.get(k) for k in ('url','document_identity','scroll')):
            raise ValueError('Post-input observation changed its original document or viewport')
        candidates=[e['element_id'] for e in before.get('elements',[]) if e.get('visible') is True
                    and e.get('inputable') and e.get('text')==label]
        if len(candidates)!=1:raise ValueError('Post-input semantic owner is missing or ambiguous')
        node=candidates[0];basis=projection(before,node,action='type')
        if (basis['value'].get('value')!=scope['expected_value']
                or basis['binding'].get('input_type')!=source['binding'].get('input_type')):
            raise ValueError('Post-input value or input identity differs from dispatched operation')
        inner=scope_for(before,node,basis['binding']['selector'],basis['binding'].get('index',0),
                        action='type',version=TYPING_VERSION)
    elif scope.get('purpose')=='post_primary_content':
        from urllib.parse import urlsplit
        if (urlsplit(before.get('url','')).hostname!=urlsplit(scope['source_url']).hostname
                or not scope['allow_navigation'] and (before.get('url')!=scope['source_url']
                or before.get('document_identity')!=scope['source_document'])):
            raise ValueError('Post-content observation lacks original document/application binding')
        inner=reading_scope(before)
    else:raise ValueError('Unknown post-action observation purpose')
    result=_pre_post_pair(before,after,png_before,png_after,inner)
    values_equal=before.get('values')==after.get('values')
    result.update(schema_version=POST_VERSION,action_scope=deepcopy(scope),
                  accepted=bool(result['accepted'] and values_equal),all_values_stable=values_equal,
                  observation_only=True,dispatch_permission=False,inner_scope=inner)
    return result


def pair(before, after, png_before, png_after, scope):
    from .dynamic_regions import enabled as dynamic_enabled,pair as dynamic_pair
    if dynamic_enabled(before) and dynamic_enabled(after):
        return dynamic_pair(before,after,png_before,png_after,action_scope=scope)
    if scope.get('schema_version') != POST_VERSION:
        return _pre_post_pair(before,after,png_before,png_after,scope)
    if scope.get('action')!='observe' or scope.get('purpose') not in ('post_search_input','post_primary_content'):
        raise ValueError('Invalid post-action observation policy')
    # An incomplete new document is an ineligible observation, not another
    # dispatch. Preserve every snapshot/PNG and use the existing read-only retry
    # budget. The ordinary acceptance proof is unchanged.
    try:
        return _post_pair(before,after,png_before,png_after,scope)
    except ValueError as error:
        from .browser import fingerprint
        with Image.open(BytesIO(png_before)) as a, Image.open(BytesIO(png_after)) as b:
            if a.format!='PNG' or b.format!='PNG' or a.size!=b.size or list(a.size)!=before['screen_resolution']:
                raise ValueError('Post observation requires complete original viewport PNGs') from error
        return {'schema_version':POST_VERSION,'action_scope':deepcopy(scope),'accepted':False,
                'reason':str(error),'full_dom_stable':fingerprint(before)==fingerprint(after),
                'related_dom_stable':False,'loading_complete':False,
                'before_fingerprint':fingerprint(before),'after_fingerprint':fingerprint(after),
                'png_before_sha256':hashlib.sha256(png_before).hexdigest(),
                'png_after_sha256':hashlib.sha256(png_after).hexdigest(),
                'observation_only':True,'dispatch_permission':False}


def validate_dynamic_scope(before,after,scope):
    """Keep original action/expected-value obligations; only variation is shared."""
    if scope is None:return True
    from .dynamic_regions import projection as content_projection
    version=scope.get('schema_version');purpose=scope.get('purpose');node=scope.get('node')
    a,b=content_projection(before,protect=[node]),content_projection(after,protect=[node])
    if version in (VERSION,TYPING_VERSION):
        if purpose not in ('first_search_focus','focused_search_type'):raise ValueError('Unknown focus purpose')
        action=scope['action']
        if projection(a,node,action=action)!=scope['basis'] or projection(b,node,action=action)!=scope['basis']:
            raise ValueError('Original focus/input basis changed')
    elif version==FOLLOWUP_VERSION:
        basis=scope['basis']
        if purpose=='observed_search_followup':
            if followup_projection(a,node,scope['action'])!=basis or followup_projection(b,node,scope['action'])!=basis:
                raise ValueError('Original follow-up identity changed')
        elif purpose=='observed_reading_scroll':
            for state in (a,b):
                if any(state.get(k)!=basis.get(k) for k in ('url','document_identity','scroll','values')):
                    raise ValueError('Original reading scope document/value changed')
                found=reading_projection(state,node)
                if found['element']!=basis['element'] or found['main_binding']!=basis['main_binding']:
                    raise ValueError('Original reading region identity changed')
        else:raise ValueError('Unknown follow-up purpose')
    elif version==POST_VERSION:
        if scope.get('action')!='observe':raise ValueError('Post scope cannot dispatch')
        if purpose=='post_search_input':
            source=scope['source'];label=source['element'].get('text')
            for state in (a,b):
                if any(state.get(k)!=source.get(k) for k in ('url','document_identity','scroll')):
                    raise ValueError('Post-input source document changed')
                matches=[e['element_id'] for e in state.get('elements',[]) if e.get('inputable') and e.get('visible') and e.get('text')==label]
                if len(matches)!=1:raise ValueError('Post-input target missing or ambiguous')
                current=projection(state,matches[0],action='type')
                if current['value'].get('value')!=scope['expected_value'] or current['binding'].get('input_type')!=source['binding'].get('input_type'):
                    raise ValueError('Post-input actual value differs from dispatched expected value')
        elif purpose in ('post_primary_content','shared_dynamic_regions'):
            from urllib.parse import urlsplit
            for state in (a,b):
                if (urlsplit(state.get('url','')).hostname!=urlsplit(scope['source_url']).hostname or
                    not scope['allow_navigation'] and (state.get('url')!=scope['source_url'] or state.get('document_identity')!=scope['source_document'])):
                    raise ValueError('Post-content original document/application differs')
        else:raise ValueError('Unknown post scope purpose')
    else:raise ValueError('Unknown dynamic comparison action scope')
    return True
