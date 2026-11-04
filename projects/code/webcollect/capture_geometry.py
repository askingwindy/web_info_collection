"""Same-frame CSS geometry tolerance; never a pixel or action-effect exemption."""
from copy import deepcopy
import math

VERSION = 'webcollect-frame-geometry-1'
MAX_CSS_EDGE = 5


def _box(value):
    return (isinstance(value, list) and len(value) == 4 and
            all(type(v) in (int, float) and math.isfinite(v) for v in value) and
            value[0] < value[2] and value[1] < value[3])


def _witness(state, cid):
    for row in state.get('geometry_witnesses', []):
        if row.get('element_id') == cid:
            return row
    # Archived image records already contain nine real hit samples. This is
    # sufficient for an offline replay, never a reconstructed browser event.
    for row in state.get('capture_images', []):
        if row.get('element_id') == cid:
            return {'element_id': cid, 'bbox': row.get('bbox'),
                    'samples': row.get('exclusion_basis', {}).get('hit_samples', [])}
    return None


def _hits(row):
    samples = row.get('samples', []) if row else []
    return (len(samples) == 9 and all(s.get('ancestor') is True and s.get('hit_tag') for s in samples))


def compare_geometry(before, after):
    """Return a comparison-only projection plus every used/rejected edge proof.

    Semantic fields, identities, hit owners, protection and image contents are
    never removed. Exact pixels and the remaining full state still gate capture.
    """
    projected = deepcopy(after); proofs = []; by_id = {}
    dpr = before.get('device_pixel_ratio', 1)
    if dpr != after.get('device_pixel_ratio', 1) or type(dpr) not in (int, float) or dpr <= 0:
        return projected, []

    def visit(a, b, path=(), cid=None):
        if isinstance(a, dict) and isinstance(b, dict):
            cid = a.get('element_id', cid)
            if a.keys() != b.keys():
                return
            for key in a:
                # Protection regions must remain identical. Do not turn a
                # layout tolerance into an occlusion or result-area exemption.
                if key in ('protected_regions', 'protected_boxes', 'unknown_paint_overlaps',
                           'unbounded_paint_sources', 'text_blocks', 'assertion_targets'):
                    continue
                if key == 'bbox' and a[key] != b[key] and cid and path and path[0] in (
                        'elements', 'capture_images', 'target', 'geometry_witnesses'):
                    old, new = a[key], b[key]
                    w1, w2 = _witness(before, cid), _witness(after, cid)
                    edges = [abs(x-y) for x,y in zip(old,new)] if _box(old) and _box(new) else [float('inf')]
                    hit_identity = (_hits(w1) and _hits(w2) and
                        [{k:v for k,v in s.items() if k != 'point'} for s in w1['samples']] ==
                        [{k:v for k,v in s.items() if k != 'point'} for s in w2['samples']])
                    accepted = bool(max(edges) <= MAX_CSS_EDGE and hit_identity)
                    proof = {'rule_version':VERSION,'element_id':cid,'path':'/'.join(map(str,path+(key,))),
                        'original_bbox':old,'recheck_bbox':new,'edge_offsets_css':edges,
                        'max_edge_offset_css':max(edges),'device_pixel_ratio':dpr,
                        'image_coordinate_scale':[1,1], 'image_coordinate_basis':'viewport_png(scale=css); delivery image is CSS-sized even when DPR differs',
                        'physical_edge_offsets':[e*dpr for e in edges],
                        'original_hit':deepcopy(w1),'recheck_hit':deepcopy(w2),
                        'accepted':accepted,'reason':'Same element and hit owner; <=5 CSS px; semantic/protection equality and independent pixel rules still mandatory.' if accepted else 'Missing hit identity or edge offset exceeds 5 CSS px.'}
                    proofs.append(proof); by_id[cid] = by_id.get(cid, True) and accepted
                    if accepted:b[key] = deepcopy(old)
                else:
                    visit(a[key],b[key],path+(key,),cid)
        elif isinstance(a,list) and isinstance(b,list) and len(a)==len(b):
            for i,(x,y) in enumerate(zip(a,b)):visit(x,y,path+(i,),cid)
    visit(before,projected)
    # Hit probes move with the very same accepted box, not independently.
    for key in ('capture_images', 'geometry_witnesses'):
        for a,b in zip(before.get(key,[]), projected.get(key,[])):
            cid=a.get('element_id')
            if not by_id.get(cid):continue
            sa = a.get('exclusion_basis',{}).get('hit_samples',[]) if key=='capture_images' else a.get('samples',[])
            sb = b.get('exclusion_basis',{}).get('hit_samples',[]) if key=='capture_images' else b.get('samples',[])
            for x,y in zip(sa,sb):
                if (len(x.get('point',[]))==2 and len(y.get('point',[]))==2 and
                        max(abs(i-j) for i,j in zip(x['point'],y['point']))<=MAX_CSS_EDGE):
                    y['point']=deepcopy(x['point'])
    return projected, proofs


def translation_regions(before, after, proofs, first, last):
    """Prove an exact translated peripheral raster over an unchanged background.

    No similarity score. The moved crop must be byte-identical and all newly
    exposed/covered pixels must have one identical background color. Text,
    results, action targets and competing controls are never exempted.
    """
    elements={e['element_id']:e for e in before.get('elements',[])}
    new={e['element_id']:e for e in after.get('elements',[])}
    result=[];seen=set()
    for proof in proofs:
        cid=proof['element_id'];e=elements.get(cid);f=new.get(cid)
        if not proof['accepted'] or cid in seen or not e or not f:continue
        seen.add(cid)
        a,b=e.get('bbox'),f.get('bbox')
        if not _box(a) or not _box(b) or not all(type(x) is int for x in a+b):continue
        dx,dy=b[0]-a[0],b[1]-a[1]
        if not (0<max(abs(dx),abs(dy))<=5 and a[2]-a[0]==b[2]-b[0] and a[3]-a[1]==b[3]-b[1]):continue
        union=[min(a[0],b[0]),min(a[1],b[1]),max(a[2],b[2]),max(a[3],b[3])]
        if not (0<=union[0]<union[2]<=first.width and 0<=union[1]<union[3]<=first.height):continue
        # Character motion can change legibility; self-painting surfaces can
        # change semantics without DOM text. Neither has an exemption here.
        if e.get('text') or e.get('element_type') in ('window','canvas','video') or e.get('native_role') in ('canvas','video','iframe'):continue
        ancestors=set();cursor=e.get('parent_id')
        while cursor in elements and cursor not in ancestors:
            ancestors.add(cursor);cursor=elements[cursor].get('parent_id')
        def overlap(x,y):return _box(x) and min(x[2],y[2])>max(x[0],y[0]) and min(x[3],y[3])>max(x[1],y[1])
        guarded=[before.get('target') or {},after.get('target') or {},
                 *before.get('assertion_targets',[]),*after.get('assertion_targets',[])]
        guarded += [x for x in [*elements.values(),*new.values()] if x['element_id']!=cid and x['element_id'] not in ancestors
                    and (x.get('text') or x.get('clickable') or x.get('inputable') or x.get('element_type') in ('image','window'))]
        # Existing explicit protection and clip proofs must remain disjoint.
        for state in (before,after):
            for image in state.get('capture_images',[]):
                if image.get('element_id')==cid:guarded+=image.get('exclusion_basis',{}).get('protected_regions',[])
        if any(overlap(x.get('bbox'),union) for x in guarded):continue
        first=first.convert('RGBA');last=last.convert('RGBA')
        if first.crop(a).tobytes()!=last.crop(b).tobytes():continue
        background=set()
        for box,im in ((a,first),(b,last)):
            for y in range(union[1],union[3]):
                for x in range(union[0],union[2]):
                    if not (box[0]<=x<box[2] and box[1]<=y<box[3]):background.add(im.getpixel((x,y)))
        if len(background)!=1:continue
        result.append({'element_id':cid,'bbox':union,'original_bbox':a,'recheck_bbox':b,
                       'translation_css':[dx,dy],'translation_image':[dx,dy],
                       'device_pixel_ratio':proof['device_pixel_ratio'],
                       'rule_version':VERSION,'reason':'Exact translated raster; unchanged uniform exposed background; disjoint target/text/results/other controls; all outside pixels checked independently.'})
    return result
