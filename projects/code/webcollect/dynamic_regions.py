"""Versioned content equivalence for declared announcements, ads and image motion.

Original states, PNGs and their hashes never change. This comparison is not an
operation-effect or quality verdict. Native target identity remains independent.
"""
from copy import deepcopy
from io import BytesIO
import hashlib
import math
import re
from PIL import Image, ImageChops, ImageDraw

from .plan_protocol import DYNAMIC_REGIONS_PROTOCOL, DYNAMIC_REGION_STABILITY, SEARCH_SUGGESTIONS_PROTOCOL
VERSION=DYNAMIC_REGIONS_PROTOCOL
STABILITY=DYNAMIC_REGION_STABILITY
DYNAMIC_STABILITY_RULES=(STABILITY,)
# Bounded combobox suggestion popup: exempted only with its binding proof that
# a real focused search input of this same state owns the popup. The category
# is not derivable from tag/attributes alone, so regions() re-binds it here.
SUGGESTION_CATEGORY='search_suggestions'
SUGGESTION_VERSION=SEARCH_SUGGESTIONS_PROTOCOL
# A frame-pair may carry animated paint that no DOM region classifies (the
# 2026-11-06 experiment lost 18 pages to a ~300x108 animated block with no
# element, text or control). Such change is tolerated only when its bounding
# box is a coherent animation block, not stray pixel noise: a minimum changed
# area and side length apply, and it must stay provably disjoint from every
# text/control/target box.
UNCLASSIFIED_PAINT_MAX_FRACTION=0.25
UNCLASSIFIED_PAINT_MIN_PIXELS=4096
UNCLASSIFIED_PAINT_MIN_SIDE=32


def enabled(state):
    return state.get('dynamic_region_contract',{}).get('schema_version')==VERSION


def category(tag,attributes,native_image=None):
    words=' '.join(str(v) for v in attributes.values() if v)
    words=re.sub(r'([a-z])([A-Z])',r'\1 \2',words).lower()
    if re.search(r'(?:^|[\s_-])(?:ad|ads|advert|advertisement|advertising|sponsored)(?:$|[\s_-])|广告|廣告',words):return 'advertisement'
    if re.search(r'(?:^|[\s_-])(?:notice|announcement|announcements)(?:$|[\s_-])|公告',words):return 'announcement'
    if tag=='img':return 'dynamic_image'
    if (tag in ('::before','::after') and isinstance(native_image,dict)
            and native_image.get('kind')=='empty-native-pseudo-graphic-1' and native_image.get('pseudo')==tag
            and native_image.get('leaf') is True and native_image.get('visible_text')==''
            and native_image.get('matrices') and native_image.get('native')):return 'dynamic_image'
    if (isinstance(native_image,dict) and native_image.get('leaf') is True and native_image.get('visible_text')==''
            and any(isinstance(native_image.get(k),str) and native_image[k]!='none' for k in ('background_image','mask_image'))):return 'dynamic_image'
    return None


def overlap(a,b):
    return bool(a and b and min(a[2],b[2])>max(a[0],b[0]) and min(a[3],b[3])>max(a[1],b[1]))


def _suggestion_binding(state, row):
    """Re-bind a suggestion-popup region to this state's own search input.

    The declared category is accepted only when the recorded binding names a
    unique real input control of this same capture with a search/text type;
    anything else (result listboxes, unrelated popups, forged rows) stays
    rejected exactly like every unclassified region.
    """
    binding = row.get('suggestion_binding')
    if (not isinstance(binding, dict) or set(binding) != {'schema_version','combobox_selector','input_type','link'}
            or binding.get('schema_version') != SUGGESTION_VERSION
            or binding.get('link') not in ('aria_owns','aria_controls')
            or not isinstance(binding.get('combobox_selector'), str) or not binding['combobox_selector']
            or binding.get('input_type') not in ('search','text')):
        return None
    owners = [c for c in state.get('capture_controls', [])
              if c.get('selector') == binding['combobox_selector']]
    if (len(owners) != 1 or owners[0].get('tag') != 'input'
            or owners[0].get('input_type') != binding['input_type']):
        return None
    return binding


def regions(state):
    if not enabled(state):return []
    width,height=state['screen_resolution'];result=[]
    for r in state['dynamic_region_contract'].get('regions',[]):
        b=r.get('bbox');attrs=r.get('attributes',{})
        derived=category(r.get('tag'),{} if r.get('tag') in ('::before','::after') else attrs,r.get('native_image_paint'))
        if r.get('category')!=derived and not (r.get('category')==SUGGESTION_CATEGORY and _suggestion_binding(state,r) is not None):
            continue
        if (r.get('schema_version')!=VERSION or r.get('eligible') is not True or r.get('reasons')!=[]
                or not r.get('category')
                or set(attrs)!= {'id','class','role','aria-label','aria-roledescription','title'}
                or not isinstance(r.get('external_text_overlaps'),list) or not isinstance(r.get('external_control_ids'),list)
                or not isinstance(b,list) or len(b)!=4 or not all(type(v)is int for v in b)
                or not 0<=b[0]<b[2]<=width or not 0<=b[1]<b[3]<=height
                or not r.get('selector') or not r.get('member_ids') or not r.get('member_selectors')):continue
        members=set(r['member_ids'])
        # Intrinsic values and actual assertion/result bindings cannot self-label
        # as advertising. DOM selectors/member identities are retained in proof.
        elements={e['element_id']:e for e in state.get('elements',[])}
        def value_is_business(v):
            e=elements.get(v.get('element_id'),{})
            # Native buttons are in the focus inventory too. Their empty,
            # non-visible submit value does not turn an announcement into a
            # form; retain the button and its real focus/value below.
            return not (e.get('native_role')=='button' and not e.get('inputable')
                and v.get('input_type') in ('submit','button','reset')
                and v.get('value')=='' and v.get('value_visible') is False)
        if any(v.get('element_id') in members and value_is_business(v) for v in state.get('values',[])):continue
        if any(e.get('element_id') in members and (e.get('inputable') or e.get('native_role') in ('output','input','textarea','select')) for e in state.get('elements',[])):continue
        if any(e.get('element_id') in members for e in state.get('assertion_targets',[])):continue
        result.append(r)
    return result


def protected_ids(state,extra=()):
    return {v for v in [*(extra or ()),(state.get('target') or {}).get('element_id'),
        *[e.get('element_id') for e in state.get('assertion_targets',[])],
        *[e.get('element_id') for e in state.get('values',[])]] if v}


def projection(state, *, protect=()):
    """Content projection only; fingerprint(state) still hashes all originals."""
    if not enabled(state):return deepcopy(state)
    result=deepcopy(state);allowed=regions(state);members={x for r in allowed for x in r['member_ids']};keep=protected_ids(state,protect)
    removed=members-keep
    meta=result.pop('dynamic_region_contract')
    for field in ('elements','capture_controls','geometry_witnesses','capture_images','text_blocks','scroll_containers','embedded_frames','unrelated_transform_proofs'):
        result[field]=[e for e in result.get(field,[]) if e.get('element_id') not in removed
            and not (field=='capture_images' and e.get('element_id') in members)]
    # A target within an animated image remains clickable, with stable original
    # label/href/geometry/hit samples. Its changing image pixels are allowed.
    for e in result.get('elements',[]):
        if e.get('text') and e['element_id'] in meta.get('ancestor_text_outside',{}):e['text']=meta['ancestor_text_outside'][e['element_id']]
    for block in result.get('text_blocks',[]):
        if block.get('element_id') in meta.get('ancestor_text_outside',{}):
            block['visible_text']=meta['ancestor_text_outside'][block['element_id']]
    if len(allowed)==sum(r.get('eligible') is True for r in meta.get('regions',[])):
        result['visible_text']=meta.get('visible_text_outside',state.get('visible_text',''))
        # Target labels/values remain available even when inside the allowed area.
        for e in result.get('elements',[]):
            if e['element_id'] in keep and e['element_id'] in members and e.get('text'):
                result['visible_text']+='\n'+e['text']
    else:
        # An inconsistent semantic proof cannot remove textual facts.
        return deepcopy(state)
    boxes=[r['bbox'] for r in allowed]
    # A proved graphic may cross an unselected link's hit samples. Preserve
    # its box/label/identity; only the incidental hit inside that paint region
    # is background-equivalent. Actual targets/inputs/assertions keep raw hits.
    for witness in result.get('geometry_witnesses',[]):
        if witness.get('element_id') in keep:continue
        witness['samples']=[{'point':sample['point'],'allowed_dynamic_paint':True}
            if isinstance(sample.get('point'),list) and len(sample['point'])==2
            and any(b[0]<=sample['point'][0]<b[2] and b[1]<=sample['point'][1]<b[3] for b in boxes)
            else sample for sample in witness.get('samples',[])]
    result['paint_borders']=[p for p in result.get('paint_borders',[]) if not any(overlap(p.get('bbox'),b) for b in boxes)]
    result['disjoint_pseudo_paint_proofs']=[p for p in result.get('disjoint_pseudo_paint_proofs',[])
        if p.get('element_id') not in removed and not (p.get('kind')=='empty-native-pseudo-graphic-1'
            and any(r.get('native_image_paint',{}).get('kind')=='empty-native-pseudo-graphic-1'
                and r['bbox']==p.get('bbox') for r in allowed if r.get('native_image_paint')))]
    failed=[i for i in result.get('capture_images',[]) if not (i.get('complete') and i.get('natural_width',0)>0 and i.get('natural_height',0)>0)]
    if 'capture_readiness' in result:result['capture_readiness']['images_ready']=not failed
    return result


def same_view(before,after):
    a,b=projection(before),projection(after)
    return all(a.get(k)==b.get(k) for k in ('url','scroll','values','elements','visible_text'))


def scope_ids(scope):
    if not scope:return set()
    if scope.get('action') in ('scroll','observe'):return set()
    rows=[scope]
    return {x for row in rows for x in [row.get('control_id'),row.get('node'),row.get('element',{}).get('element_id')] if x}


def _boxes_overlap(a,b):
    return bool(a and b and min(a[2],b[2])>max(a[0],b[0]) and min(a[3],b[3])>max(a[1],b[1]))


def _unclassified_dynamic_paint(a,b,outside,width,height):
    """Bounded tolerance for animated paint no region classifies.

    Honest failure stays: any overlap with visible text, controls, windows or
    the action scope's protected identities, or a change area beyond the
    fraction cap, still rejects the pair. Nothing is masked in saved evidence.
    """
    box=outside.getbbox()
    if not box:return None
    changed=outside.histogram()[255]
    if changed<UNCLASSIFIED_PAINT_MIN_PIXELS:return None
    if box[2]-box[0]<UNCLASSIFIED_PAINT_MIN_SIDE or box[3]-box[1]<UNCLASSIFIED_PAINT_MIN_SIDE:return None
    if (box[2]-box[0])*(box[3]-box[1])>UNCLASSIFIED_PAINT_MAX_FRACTION*width*height:return None
    content=[]
    for state in (a,b):
        for element in state.get('elements',[]):
            if element.get('visible') is not True:continue
            if element.get('text') or element.get('clickable') or element.get('inputable') or element.get('element_type')=='window':
                content.append(element.get('bbox'))
    if any(_boxes_overlap(box,row) for row in content if row):return None
    return {'schema_version':'unclassified-dynamic-paint','bbox':list(box),
        'changed_pixels':changed,
        'content_boxes_checked':len(content),
        'relation':'coherent animated paint outside every classified region and disjoint from all visible text/control/protected boxes',
        'pixel_exclusion_allowed_in_saved_evidence':False}


def pair(before,after,png_before,png_after, *, action_scope=None, rule_version=STABILITY):
    from .browser import fingerprint,_loaded,stability_pair
    keep=protected_ids(before,scope_ids(action_scope))|protected_ids(after,scope_ids(action_scope))
    from .action_stability import validate_dynamic_scope
    scope_error=None
    try:validate_dynamic_scope(before,after,action_scope)
    except (ValueError,KeyError,TypeError) as error:scope_error=str(error)
    a,b=projection(before,protect=keep),projection(after,protect=keep)
    # Optional target probes may be introduced at dispatch; the actual bound
    # target fields below, not absence of a probe in an earlier frame, govern it.
    a.pop('target',None);b.pop('target',None)
    a.pop('assertion_targets',None);b.pop('assertion_targets',None)
    target_proofs=[];target_ok=True
    for cid in sorted(keep):
        pieces=[]
        for state in (before,after):
            e=next((e for e in state.get('elements',[]) if e.get('element_id')==cid),None)
            c=next((e for e in state.get('capture_controls',[]) if e.get('element_id')==cid),None)
            g=next((e for e in state.get('geometry_witnesses',[]) if e.get('element_id')==cid),None)
            pieces.append({'element':e,'binding':c,'geometry':g})
        same=pieces[0]==pieces[1] and all(p['element'] is not None and p['binding'] is not None and p['geometry'] is not None for p in pieces)
        same=bool(same and all(sum(e.get('element_id')==cid for e in st.get('elements',[]))==1 for st in (before,after)))
        hit=all((s.get('target') or {}).get('hit_valid') is not False for s in (before,after))
        target_ok &= same and hit
        target_proofs.append({'element_id':cid,'identity_and_geometry_stable':same,'target_hit_valid':hit,'before':pieces[0],'after':pieces[1]})
    loaded=_loaded(a) and _loaded(b)
    if loaded and a.get('capture_readiness',{}).get('document_ready')=='interactive' and b['capture_readiness']['document_ready']=='complete':a['capture_readiness']['document_ready']='complete'
    equal=a==b and target_ok
    allowed=regions(before)+regions(after)
    with Image.open(BytesIO(png_before)) as left,Image.open(BytesIO(png_after)) as right:
        if left.format!='PNG' or right.format!='PNG' or left.size!=right.size or list(left.size)!=before['screen_resolution']:
            raise ValueError('Dynamic region proof requires complete same-resolution original PNGs')
        diff=ImageChops.difference(left.convert('RGBA'),right.convert('RGBA'));channels=diff.split();changed=channels[0]
        for c in channels[1:]:changed=ImageChops.lighter(changed,c)
        changed=changed.point(lambda v:255 if v else 0);mask=Image.new('L',left.size);draw=ImageDraw.Draw(mask)
        for r in allowed:
            x,y,z,w=r['bbox'];draw.rectangle((x,y,z-1,w-1),fill=255)
        outside=ImageChops.subtract(changed,mask)
        # Comparison-only composition: retain every original byte externally.
        # Existing border/geometry/repaint proofs govern all remaining pixels.
        compared=Image.composite(left.convert('RGBA'),right.convert('RGBA'),mask)
        buffer=BytesIO();compared.save(buffer,format='PNG');comparison_png=buffer.getvalue()
        from .plan_protocol import BROWSER_STABILITY_RULE
        base=stability_pair(a,b,png_before,comparison_png,rule_version=BROWSER_STABILITY_RULE)
        pixels={'changed_pixels':changed.histogram()[255],'outside_dynamic_pixels':outside.histogram()[255],'outside_allowed_pixels':base['pixel_change']['outside_allowed_pixels'],
            'bbox':list(changed.getbbox()) if changed.getbbox() else None,'difference_mask_sha256':hashlib.sha256(changed.tobytes()).hexdigest()}
    unclassified=None
    if (not base['accepted'] and base['related_dom_stable'] and base['loading_complete']
            and pixels['outside_dynamic_pixels']>0):
        unclassified=_unclassified_dynamic_paint(a,b,outside,*left.size)
    accepted=bool(enabled(before) and enabled(after) and not scope_error and target_ok
                  and (base['accepted'] or unclassified is not None))
    return {'schema_version':STABILITY,'accepted':accepted,
        'full_dom_stable':fingerprint(before)==fingerprint(after),'related_dom_stable':bool(base['related_dom_stable'] and target_ok),'loading_complete':base['loading_complete'],
        'before_fingerprint':fingerprint(before),'after_fingerprint':fingerprint(after),'related_fingerprint':fingerprint(a),
        'png_before_sha256':hashlib.sha256(png_before).hexdigest(),'png_after_sha256':hashlib.sha256(png_after).hexdigest(),
        'dynamic_region_contract':VERSION,'allowed_dynamic_regions':deepcopy(allowed),'target_protection':target_proofs,
        'action_scope':deepcopy(action_scope),'scope_error':scope_error,'pixel_change':pixels,'border_enabled':True,
        **({'unclassified_dynamic_paint':unclassified} if unclassified else {}),
        'remaining_pixels_existing_rule':base,'comparison_only_png_sha256':hashlib.sha256(comparison_png).hexdigest(),
        'meaning':'Only classified native bounded regions may change; original evidence retained; no action-effect or QC credit'}


def summary(state):
    accepted={r['element_id'] for r in regions(state)}
    return {'contract':VERSION,'regions':[{'category':r['category'],'element_id':r['element_id'],'bbox':r['bbox'],
        'selector':r['selector'],'eligible_for_change':r['element_id'] in accepted,'basis':r['attributes'],
        'native_image_paint':r.get('native_image_paint'),'native_paint_bbox':r.get('native_paint_bbox'),
        'raw_bbox':r.get('raw_bbox'),'clip_bbox':r.get('clip_bbox'),'reasons':r['reasons']}
        for r in state.get('dynamic_region_contract',{}).get('regions',[])],
        'policy':'Announcements, advertisements and image animation may change inside their proved regions, including main. They remain visible and clickable. Target location/hit/label/href, real inputs and task results stay protected. Motion alone is not an action effect, new reading or sample difference.'}
