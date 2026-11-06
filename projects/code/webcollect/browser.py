"""真实浏览器只读观察与显式动作执行；不使用 locator 自动滚动或 fill 隐式聚焦。"""
import asyncio
import base64
import hashlib
from importlib.resources import files
import json
import math
import time
import weakref
from copy import deepcopy
from pathlib import Path
from PIL import Image, ImageChops, ImageDraw
from io import BytesIO

SNAPSHOT_JS=files('webcollect').joinpath('snapshot.js').read_text(encoding='utf-8')
POINTER={'click','double_click','right_click','drag','select','scroll'}
CONTROL={'click','double_click','right_click','drag','select','type'}
_SCREENSHOT_SESSIONS=weakref.WeakKeyDictionary()
_CAPTURE_FRAMES=weakref.WeakKeyDictionary()
CAPTURE_VERSION='webcollect-capture-2'
STABILITY_V2='webcollect-related-stability-2'
STABILITY_V3='webcollect-related-stability-3'
# v4: the repaint-noise guard now keys on the element tag (native_role) and
# 'window'-typed opaque frames, not on element_type alone. Canvas/video/iframe
# tags previously defaulted to 'text' and escaped their intended guard set, so
# genuine self-painting content changes could pass as compact repaint noise.
STABILITY_V4='webcollect-related-stability-4'
STABILITY_V5='webcollect-related-stability-5'
STABILITY_VERSION='webcollect-related-stability-6'
STABILITY_RULES=('webcollect-related-stability-1',STABILITY_V2,STABILITY_V3,STABILITY_V4,STABILITY_V5,STABILITY_VERSION)
# Compact repaint-noise bounds, verified by the fixture set in
# test_related_capture_stability: antialias/underline strips stay thin in one
# dimension, tiny in area, low-amplitude, and away from text/interactive boxes.
_NOISE_MAX_COMPONENTS=4
_NOISE_MAX_POINTS=96
_NOISE_MAX_LONG_EDGE=384
_NOISE_MAX_SHORT_EDGE=8
# Self-painting surfaces whose repaint is real content, never exempted as
# noise: opaque frames render as element_type 'window', and canvas/video/
# iframe/embed/object tags carry their tag in native_role.
_SELF_PAINTING_ROLES=('canvas','video','iframe','frame','embed','object')


class EvidenceStale(ValueError):
    """Synchronized state/pixels changed between evidence and execution."""
    responsibility = 'collector'
    recoverable_before_dispatch = True


class PlanViewportInfeasible(ValueError):
    """The compiled plan interacts with a control outside the current viewport.

    Planning/compilation responsibility: the page merely rendered; the step
    order did not expose the target first. Never a site business failure.
    """
    responsibility = 'collector'


class PlanLabelUnreadable(ValueError):
    """The plan's target label is not fully visible at execution time.

    Planning responsibility: the fragment cited a control whose visible label
    evidence does not cover the planned label (e.g. clipped by the fold or a
    collapsed container). The page itself remains usable — this is a task-level
    replan signal, never a whole-site failure.
    """
    responsibility = 'model'
    recoverable_before_dispatch = True

_CAPTURE_RETRY_DELAYS=(0.1,0.25,0.5,1.0,1.5,2.0,2.5)
_CAPTURE_WAIT_BUDGET=8.0
_ANIMATION_OBSERVATION_JS=r'''() => {
  const encode=value=>{
    if(typeof value==='number'&&!Number.isFinite(value))return String(value);
    if(Array.isArray(value))return value.map(encode);
    if(value&&typeof value==='object')return Object.fromEntries(Object.entries(value).map(([k,v])=>[k,encode(v)]));
    return value;
  };
  const visible=element=>{
    if(!(element instanceof Element))return false;
    if(element.checkVisibility&&!element.checkVisibility({checkOpacity:true,checkVisibilityCSS:true}))return false;
    for(let n=element;n;n=n.parentElement){const s=getComputedStyle(n);if(s.display==='none'||s.visibility!=='visible'||Number(s.opacity)===0)return false;}
    const r=element.getBoundingClientRect();return r.width>0&&r.height>0&&r.right>0&&r.bottom>0&&r.left<innerWidth&&r.top<innerHeight;
  };
  const animations=[];
  for(const animation of document.getAnimations()){
    const effect=animation.effect,target=effect?.target;if(!visible(target))continue;
    const r=target.getBoundingClientRect();
    animations.push(encode({kind:animation.constructor.name,play_state:animation.playState,pending:animation.pending,
      current_time:animation.currentTime,current_time_type:typeof animation.currentTime,playback_rate:animation.playbackRate,
      start_time:animation.startTime,timing:effect.getTiming(),computed_timing:effect.getComputedTiming(),
      composite:effect.composite,iteration_composite:effect.iterationComposite,pseudo_element:effect.pseudoElement||null,
      keyframes:effect.getKeyframes(),target:{tag:target.localName,id:target.id,rect:{x:r.x,y:r.y,width:r.width,height:r.height}}}));
  }
  return {observed_at_performance_ms:performance.now(),visible_animations:animations,
    read_only:true,occlusion_verified:false,
    scope:'Viewport-intersecting/style-visible native animation timing advice only; no occlusion or capture stability proof. Full-state fingerprint equality remains mandatory.'};
}'''


def _finite_number(value):
    return type(value) in (int,float) and math.isfinite(value)


def _merge_intervals(intervals):
    merged=[]
    for start,end in sorted(intervals):
        if end<=start:continue
        if merged and start<=merged[-1][1]+1e-6:merged[-1][1]=max(merged[-1][1],end)
        else:merged.append([start,end])
    return merged


def _native_animation_window(observation,remaining_ms,required_ms=1000, *, png_phase=False):
    """Prove a common native hold interval; this never certifies a capture."""
    guard=50.0
    horizon=remaining_ms+required_ms+guard*2
    common=[[0.0,horizon]];details=[];unsupported=[]
    for index,animation in enumerate(observation.get('visible_animations',[])):
        detail={'animation_index':index,'target':animation.get('target'),'intervals_relative_ms':[]}
        details.append(detail)
        if animation.get('play_state')!='running' and not animation.get('pending'):
            detail['status']='not_running_no_wait_needed';continue
        timing=animation.get('timing',{});current=animation.get('current_time');rate=animation.get('playback_rate')
        pseudo = animation.get('pseudo_element')
        pulse = png_phase and pseudo in ('::before','::after') and animation.get('kind') == 'CSSAnimation'
        if (animation.get('pending') or (pseudo and not pulse) or
            not _finite_number(current) or not _finite_number(rate) or rate<=0 or
            not _finite_number(animation.get('start_time'))):
            unsupported.append(index);detail.update(status='unsupported',reason='Pending/pseudo/non-numeric timeline or non-positive rate.');continue
        intervals=[]
        if animation.get('kind')=='CSSTransition':
            end=animation.get('computed_timing',{}).get('endTime')
            if _finite_number(end) and timing.get('direction')=='normal':
                intervals=[[max(0.0,(end-current)/rate),horizon]]
                detail['status']='finite_transition_natural_end'
            else:
                unsupported.append(index);detail.update(status='unsupported',reason='Transition end/direction is not provable.');continue
        else:
            duration=timing.get('duration');delay=timing.get('delay',0)
            if (timing.get('iterations')!='Infinity' or timing.get('direction')!='normal' or timing.get('easing')!='linear' or
                timing.get('iterationStart',0)!=0 or animation.get('composite') not in ['replace','auto'] or
                animation.get('iteration_composite') not in [None,'replace'] or
                not _finite_number(duration) or duration<=0 or not _finite_number(delay) or current<delay):
                unsupported.append(index);detail.update(status='unsupported',reason='Only normal linear replace infinite timing after delay is supported.');continue
            keyframes=animation.get('keyframes',[])
            properties=set().union(*(set(frame)-{'offset','computedOffset','easing','composite'} for frame in keyframes)) if keyframes else set()
            offsets=[frame.get('computedOffset') for frame in keyframes]
            valid=(len(keyframes)>=2 and bool(properties) and all(_finite_number(x) and 0<=x<=1 for x in offsets) and
                   offsets==sorted(offsets) and offsets[0]==0 and offsets[-1]==1 and
                   all(frame.get('composite') in ['auto','replace'] for frame in keyframes))
            if not valid:
                unsupported.append(index);detail.update(status='unsupported',reason='Complete replace keyframes with numeric offsets and actual properties required.');continue
            holds=[]
            for left,right in zip(keyframes,keyframes[1:]):
                if pulse:
                    # Opacity may change while a pseudo-element has zero painted area.
                    # This is scheduling advice only. Compare every original pixel.
                    hold = (properties <= {'transform','opacity'} and
                            left.get('transform') == right.get('transform') == 'scale(0)')
                else:
                    hold = all(key in left and key in right and left[key]==right[key] for key in properties)
                if hold:
                    holds.append([left['computedOffset'],right['computedOffset']])
            holds=_merge_intervals(holds);detail['hold_offsets']=holds;detail['compared_properties']=sorted(properties)
            if not holds:
                unsupported.append(index);detail.update(status='unsupported',reason='No identical-property keyframe interval.');continue
            if holds==[[0,1]]:
                intervals=[[0.0,horizon]]
            else:
                # A short period cannot supply a long hold unless every frame
                # is constant (handled above). Avoid unbounded cycle expansion.
                if duration/rate<required_ms+guard*2:
                    unsupported.append(index);detail.update(status='unsupported',reason='No period is long enough for the required guarded hold.');continue
                cycle=math.floor((current-delay)/duration)
                for iteration in range(cycle-1,cycle+math.ceil(horizon*rate/duration)+3):
                    for start,end in holds:
                        a=(delay+(iteration+start)*duration-current)/rate
                        b=(delay+(iteration+end)*duration-current)/rate
                        if b>0 and a<horizon:intervals.append([a,min(b,horizon)])
                intervals=_merge_intervals(intervals)
                intervals=[[a,b] for a,b in intervals if b-max(0,a)>=required_ms+guard*2]
            if not intervals:
                detail.update(status='no_long_hold_in_current_horizon',reason='Known hold cannot satisfy the current horizon/budget.')
            else:detail['status']='infinite_identical_property_hold'
        # Both hold edges are guarded; a finite transition already ended needs
        # no extra delay. The window is advice only, not semantic acceptance.
        guarded=[[max(0,a+guard) if a>0 else 0,b-guard] for a,b in intervals if b-guard-max(0,a+guard if a>0 else 0)>=required_ms]
        detail['intervals_relative_ms']=guarded
        common=_merge_intervals([[max(a,c),min(b,d)] for a,b in common for c,d in guarded if min(b,d)-max(a,c)>=required_ms])
    if unsupported:
        return {'status':'unsupported','unsupported_animation_indices':unsupported,'details':details,'wait_ms':0,'prediction_is_not_capture_acceptance':True}
    choices=[(max(0,a),b) for a,b in common if b-max(0,a)>=required_ms and max(0,a)<=remaining_ms]
    if not choices:
        return {'status':'no_common_window_within_budget','details':details,'wait_ms':0,'prediction_is_not_capture_acceptance':True}
    start,end=min(choices)
    return {'status':'native_window_predicted' if details else 'no_running_native_animation_wait',
            'wait_ms':start,'common_window_relative_ms':[start,end],'required_hold_ms':required_ms,
            'details':details,'prediction_is_not_capture_acceptance':True}


async def _wait_for_native_window(page,remaining_ms,required_ms, *, png_phase=False):
    result={'observations':[],'requested_wait_ms':0.0,'observed_wait_ms':0.0}
    # Recheck actual native timing after waiting. A prediction is never a
    # substitute for the unchanged before/PNG/after fingerprint comparison.
    for _ in range(2):
        try:observation=await asyncio.wait_for(page.evaluate(_ANIMATION_OBSERVATION_JS),timeout=3)
        except Exception as error:
            result['status']='native_reader_unavailable';result['reader_error']=str(error);return result
        plan=_native_animation_window(observation,max(0,remaining_ms-result['requested_wait_ms']),required_ms,png_phase=png_phase)
        result['observations'].append({'native':observation,'plan':plan})
        delay=plan['wait_ms']
        if delay<=0:
            result['status']=plan['status'];return result
        started=time.monotonic();await asyncio.sleep(delay/1000)
        result['observed_wait_ms']+=(time.monotonic()-started)*1000
        result['requested_wait_ms']+=delay
    result['status']='window_recheck_not_confirmed';return result


def fingerprint(state):
    return hashlib.sha256(json.dumps(state,ensure_ascii=False,sort_keys=True).encode()).hexdigest()


def _loaded(state):
    ready=state.get('capture_readiness',{})
    # DOMContentLoaded establishes the document tree. Pending offscreen/background
    # requests do not prove that visible task content is unloaded. Fonts, viewport
    # images, synchronized state/pixels and the pre-action recheck remain required.
    return (ready.get('schema_version')=='webcollect-capture-readiness-1'
            and ready.get('document_ready') in ('interactive', 'complete')
            and ready.get('fonts_ready') is True and ready.get('images_ready') is True)


def _image_regions(state, *, unloaded=False):
    width,height=state['screen_resolution'];regions=[]
    def box_ok(box):
        return (isinstance(box,list) and len(box)==4 and all(type(n) in (int,float) and math.isfinite(n) for n in box)
                and box[0]<box[2] and box[1]<box[3])
    def overlaps(a,b):return box_ok(a) and box_ok(b) and min(a[2],b[2])>max(a[0],b[0]) and min(a[3],b[3])>max(a[1],b[1])
    for image in state.get('capture_images',[]):
        box=image.get('bbox')
        if not box_ok(box) or not all(type(n) is int for n in box) or not (0<=box[0]<box[2]<=width and 0<=box[1]<box[3]<=height):continue
        basis=image.get('exclusion_basis',{});attributes=basis.get('attributes',{})
        clip=basis.get('clip_bbox');protected=basis.get('protected_regions')
        points=[[x,y] for x in (box[0]+.5,(box[0]+box[2])/2,box[2]-.5)
                for y in (box[1]+.5,(box[1]+box[3])/2,box[3]-.5)]
        critical=[state.get('target'),*state.get('assertion_targets',[])]
        critical += [e for e in state.get('elements',[]) if e.get('element_id')!=image.get('element_id') and
                     (e.get('clickable') or e.get('inputable') or e.get('text') or e.get('element_type') in ('image','window'))]
        proved=(basis.get('schema_version')=='webcollect-decorative-image-basis-1'
                and attributes.get('alt')=='' and attributes.get('aria-hidden')=='true'
                and attributes.get('role') in ('presentation','none')
                and all(k in attributes and attributes[k] is None for k in ('title','aria-label','aria-labelledby'))
                and basis.get('pointer_events')=='none' and basis.get('ancestor_exclusions')==[]
                and basis.get('unknown_paint_overlaps')==[]
                and basis.get('unbounded_paint_sources')==[]
                and basis.get('protected_overlap') is False and basis.get('text_or_control_overlap') is False
                and box_ok(clip) and clip[0]<=box[0] and clip[1]<=box[1] and clip[2]>=box[2] and clip[3]>=box[3]
                and isinstance(protected,list) and all(isinstance(p,dict) and 'bbox' in p
                    and p.get('contains_image') is False and p.get('inside_image') is False and not overlaps(box,p['bbox']) for p in protected)
                and not any(isinstance(e,dict) and overlaps(box,e.get('bbox')) for e in critical)
                and len(basis.get('hit_samples',[]))==9
                and [h.get('point') for h in basis['hit_samples']]==points
                and all(h.get('ancestor') is True and h.get('hit_tag') for h in basis['hit_samples']))
        readiness=(image.get('eligible') is True and image.get('exclusion_reasons')==[] and image.get('complete') is True
                   and image.get('natural_width',0)>0 and image.get('natural_height',0)>0)
        if unloaded:
            readiness=(image.get('exclusion_reasons')==['image_not_loaded'] and image.get('complete') is True
                       and image.get('natural_width')==0 and image.get('natural_height')==0)
        if (readiness
                and proved
                and isinstance(box,list) and len(box)==4 and all(type(x) is int for x in box)
                and 0<=box[0]<box[2]<=width and 0<=box[1]<box[3]<=height):
            regions.append({'element_id':image['element_id'],'bbox':box})
    return regions


def _unrelated_failed_images(state):
    """Failed images whose own exclusion evidence proves they occupy no target,
    result, visible text or control area, with no unknown paint or coverage.

    A readiness-only exemption: the exact-pixel comparison never masks their
    blank boxes, and images related to the task's protected content stay held.
    """
    safe=set()
    for image in state.get('capture_images',[]):
        reasons=image.get('exclusion_reasons')
        if not isinstance(reasons,list) or 'image_not_loaded' not in reasons:
            continue
        if not (image.get('complete') is True and image.get('natural_width')==0
                and image.get('natural_height')==0):
            continue
        basis=image.get('exclusion_basis',{})
        samples=basis.get('hit_samples')
        if (not isinstance(basis,dict) or basis.get('schema_version')!='webcollect-decorative-image-basis-1'
                or basis.get('protected_overlap') is True
                or basis.get('text_or_control_overlap') is True
                or basis.get('unknown_paint_overlaps')
                or basis.get('unbounded_paint_sources')
                or 'covered_or_unknown_hit' in reasons
                or not isinstance(samples,list)
                or not all(isinstance(h,dict) and h.get('ancestor') is True for h in samples)):
            continue
        safe.add(image['element_id'])
    return safe


def _media_regions(state):
    width,height=state['screen_resolution'];regions=[]
    for media in state.get('capture_media',[]):
        box=media.get('bbox');proof=media.get('proof',{})
        if not (media.get('kind')=='peripheral_video' and media.get('eligible') is True
                and media.get('ready') is True and media.get('actions_supported') is False
                and proof.get('schema_version')=='webcollect-peripheral-video-1'
                and proof.get('peripheral') is True and proof.get('controls') is False
                and proof.get('geometry_and_style_clear') is True
                and proof.get('hit_samples')==[True]*9 and isinstance(box,list) and len(box)==4
                and all(type(n) is int for n in box) and 0<=box[0]<box[2]<=width and 0<=box[1]<box[3]<=height):
            continue
        guards=proof.get('protected_boxes')
        if not isinstance(guards,list) or any(not isinstance(b,list) or len(b)!=4 or
                min(box[2],b[2])>max(box[0],b[0]) and min(box[3],b[3])>max(box[1],b[1]) for b in guards):
            continue
        regions.append({'kind':'peripheral_video','bbox':box})
    return regions


def related_projection(state):
    """Drop only source strings with a complete read-only decorative-image proof."""
    result=deepcopy(state)
    allowed={r['element_id'] for r in _image_regions(state)}
    for image in result.get('capture_images',[]):
        if image.get('element_id') in allowed:
            image['src']=image['current_src']='BOUNDED_DECORATIVE_IMAGE_SOURCE'
    return result


def stability_pair(before,after,png_before,png_after, *, rule_version=None, allow_border=True, action_scope=None):
    """Recomputable full-state and exact-pixel proof; never mask saved evidence."""
    from .dynamic_regions import STABILITY as dynamic_rule, enabled as dynamic_enabled, pair as dynamic_pair
    if rule_version==dynamic_rule or (rule_version is None and dynamic_enabled(before) and dynamic_enabled(after)):
        return dynamic_pair(before,after,png_before,png_after,action_scope=action_scope)
    from .action_stability import VERSIONS as focus_versions, pair as focus_pair
    if action_scope is not None or rule_version in focus_versions:
        if action_scope is None:raise ValueError('Scoped proof requires its frozen action scope')
        return focus_pair(before,after,png_before,png_after,action_scope)
    full=fingerprint(before)==fingerprint(after)
    rule_version=rule_version or STABILITY_VERSION
    if rule_version not in STABILITY_RULES:raise ValueError('Unknown stability rule')
    left,right=related_projection(before),related_projection(after)
    loading_proof=[];geometry_proof=[]
    if rule_version==STABILITY_VERSION:
        # Readiness exceptions do not exempt a single image pixel. A failed
        # glyph, semantic image, control, overlap or incomplete proof stays held.
        for original,projected in ((before,left),(after,right)):
            failed=[i for i in original.get('capture_images',[]) if not
                    (i.get('complete') and i.get('natural_width',0)>0 and i.get('natural_height',0)>0)]
            safe={r['element_id'] for r in _image_regions(original,unloaded=True)}
            safe |= _unrelated_failed_images(original)
            if failed and all(i.get('element_id') in safe for i in failed):
                projected['capture_readiness']['images_ready']=True
                loading_proof.append({'state_fingerprint':fingerprint(original),'images':deepcopy(failed),
                    'reason':'Failed images carry their own proof of being disjoint from target, results, text, controls and unknown paint; pixels remain exact.'})
        from .capture_geometry import compare_geometry
        right,geometry_proof=compare_geometry(left,right)
    loaded=_loaded(left) and _loaded(right)
    if rule_version in (STABILITY_V2,STABILITY_V3,STABILITY_V4,STABILITY_V5,STABILITY_VERSION) and loaded and before['capture_readiness']['document_ready']=='interactive' and after['capture_readiness']['document_ready']=='complete':
        left['capture_readiness']['document_ready']='complete'
    related=loaded and left==right
    regions=_image_regions(before) if related else []
    media_regions=_media_regions(before) if related and rule_version in (STABILITY_V5,STABILITY_VERSION) else []
    with Image.open(BytesIO(png_before)) as first,Image.open(BytesIO(png_after)) as last:
        if first.format!='PNG' or last.format!='PNG' or list(first.size)!=before['screen_resolution'] or first.size!=last.size:
            raise ValueError('同步像素证明需要相同视口分辨率的完整原始PNG')
        channels=ImageChops.difference(first.convert('RGBA'),last.convert('RGBA')).split()
        diff=channels[0]
        for channel in channels[1:]:diff=ImageChops.lighter(diff,channel)
        changed=diff.point(lambda value:255 if value else 0)
        mask=Image.new('L',first.size,0);draw=ImageDraw.Draw(mask)
        geometry_regions=[]
        if rule_version==STABILITY_VERSION and related:
            from .capture_geometry import translation_regions
            geometry_regions=translation_regions(before,after,geometry_proof,first,last)
        for region in regions+media_regions+geometry_regions:
            x1,y1,x2,y2=region['bbox'];draw.rectangle((x1,y1,x2-1,y2-1),fill=255)
        # New receipts only. Never reinterpret v1 failures. A local edge proof
        # and unchanged full semantic state are necessary; no whole-page score.
        border_proof=[]
        if rule_version in (STABILITY_V2,STABILITY_V3,STABILITY_V4,STABILITY_V5,STABILITY_VERSION) and related and allow_border:
            rgba_first,rgba_last=first.convert('RGBA'),last.convert('RGBA')
            for region in before.get('paint_borders',[]):
                box=region['bbox'];edges=region['edges']
                if len(box)!=4 or len(edges)!=4:continue
                points=set()
                for x1,y1,x2,y2 in edges:
                    for x in range(max(0,x1),min(first.width,x2)):
                        for y in range(max(0,y1),min(first.height,y2)):
                            if changed.getpixel((x,y)) and not mask.getpixel((x,y)):points.add((x,y))
                # Bound changed area relative to the proved border perimeter,
                # and amplitude to one sixteenth of the channel range.
                perimeter=2*((box[2]-box[0])+(box[3]-box[1]))
                if not points or len(points)>perimeter/64:continue
                deltas=[]
                for point in points:
                    a,b=rgba_first.getpixel(point),rgba_last.getpixel(point)
                    delta=[b[i]-a[i] for i in range(3)]
                    if a[3]!=b[3] or max(map(abs,delta))>255/16 or max(delta)-min(delta)>1:break
                    deltas.append(delta)
                else:
                    for point in points:mask.putpixel(point,255)
                    border_proof.append({'bbox':box,'points':[list(point) for point in sorted(points)],'rgb_deltas':deltas,
                                         'rule':'plain-nontask-border-low-contrast-1'})
        # v3/v4 only, never a reinterpretation of recorded v1/v2 failures: a
        # fully identical DOM fingerprint (values, text, geometry, readiness)
        # cannot hide a character, focus, checkbox or layout change — those all
        # alter the fingerprint. What remains is sub-pixel repaint noise on
        # untracked lines, tolerated only when compact, low-amplitude and away
        # from every text/interactive element box.
        paint_noise_proof=[]
        if (rule_version in (STABILITY_V3,STABILITY_V4,STABILITY_V5,STABILITY_VERSION) and allow_border and related and full
                and before['capture_readiness'].get('document_ready')=='complete'):
            rgba_first,rgba_last=first.convert('RGBA'),last.convert('RGBA')
            guard=[]
            for element in before.get('elements',[]):
                # DOM-backed text and control values cannot change under an
                # identical fingerprint; only self-painting surfaces can, and
                # those boxes stay guarded. v3 keyed on element_type, which
                # canvas/video/iframe tags never receive (they default to
                # 'text'); v4 additionally guards by native_role and opaque
                # 'window' frames so real repaints of embedded paint surfaces
                # are never exempted by the small-pixel threshold. v3 receipts
                # keep their exact original guard on revalidation.
                if rule_version==STABILITY_V3:
                    if element.get('element_type') not in ('image','canvas','video','iframe','embed','object'):
                        continue
                else:
                    role=(element.get('native_role') or '').lower()
                    if (element.get('element_type') not in ('image','canvas','video','iframe','embed','object')
                            and element.get('element_type')!='window'
                            and role not in _SELF_PAINTING_ROLES):
                        continue
                box=element.get('bbox')
                if isinstance(box,list) and len(box)==4 and box[2]-2>box[0] and box[3]-2>box[1]:
                    guard.append((box[0]+1,box[1]+1,box[2]-1,box[3]-1))
            remaining={(x,y) for x in range(first.width) for y in range(first.height)
                       if changed.getpixel((x,y)) and not mask.getpixel((x,y))}
            components=[]
            while remaining:
                if len(components)>=_NOISE_MAX_COMPONENTS:break
                seed=next(iter(remaining));stack=[seed];component=[];remaining.discard(seed)
                while stack:
                    x,y=stack.pop();component.append((x,y))
                    for nx,ny in ((x+1,y),(x-1,y),(x,y+1),(x,y-1),(x+1,y+1),(x-1,y-1),(x+1,y-1),(x-1,y+1)):
                        if (nx,ny) in remaining:remaining.discard((nx,ny));stack.append((nx,ny))
                components.append(component)
            compliant=[]
            for component in components:
                if len(component)>_NOISE_MAX_POINTS:continue
                xs=[p[0] for p in component];ys=[p[1] for p in component]
                box=(min(xs),min(ys),max(xs)+1,max(ys)+1)
                thin=min(box[2]-box[0],box[3]-box[1])<=_NOISE_MAX_SHORT_EDGE
                short=max(box[2]-box[0],box[3]-box[1])<=_NOISE_MAX_LONG_EDGE
                if not (thin and short):continue
                deltas=[];ok=True
                for x,y in component:
                    if any(gx1<=x<gx2 and gy1<=y<gy2 for gx1,gy1,gx2,gy2 in guard):ok=False;break
                    a,b=rgba_first.getpixel((x,y)),rgba_last.getpixel((x,y))
                    delta=[b[i]-a[i] for i in range(3)]
                    # Amplitude bound only: antialiased colored edges shift channels
                    # unevenly (e.g. blue borders); DOM identity plus the small
                    # per-channel bound carries the safety here.
                    if a[3]!=b[3] or max(map(abs,delta))>255/16:ok=False;break
                    deltas.append(delta)
                if ok:compliant.append((component,box,deltas))
            if not remaining and len(compliant)==len(components):
                for component,box,deltas in compliant:
                    for x,y in component:mask.putpixel((x,y),255)
                    paint_noise_proof.append({'bbox':list(box),'points':[list(point) for point in sorted(component)],'rgb_deltas':deltas,
                                              'rule':'compact-repaint-noise-v2' if rule_version in (STABILITY_V4,STABILITY_V5,STABILITY_VERSION) else 'compact-repaint-noise-v1'})
        outside=ImageChops.subtract(changed,mask)
        pixel_change={'changed_pixels':changed.histogram()[255],
                      'bbox':list(changed.getbbox()) if changed.getbbox() else None,
                      'outside_allowed_pixels':outside.histogram()[255],
                      'difference_mask_sha256':hashlib.sha256(changed.tobytes()).hexdigest()}
    return {'schema_version':rule_version,'accepted':bool(related and not pixel_change['outside_allowed_pixels']),
            'full_dom_stable':full,'related_dom_stable':bool(related),'loading_complete':bool(loaded),
            'before_fingerprint':fingerprint(before),'after_fingerprint':fingerprint(after),
            'related_fingerprint':fingerprint(related_projection(before)),
            'png_before_sha256':hashlib.sha256(png_before).hexdigest(),'png_after_sha256':hashlib.sha256(png_after).hexdigest(),
            'allowed_image_regions':regions,**({'allowed_media_regions':media_regions} if rule_version in (STABILITY_V5,STABILITY_VERSION) else {}),**({'border_proof':border_proof,'border_enabled':allow_border} if rule_version in (STABILITY_V2,STABILITY_V3,STABILITY_V4,STABILITY_V5,STABILITY_VERSION) else {}),
            **({'geometry_proof':geometry_proof,'geometry_pixel_proof':geometry_regions,'unloaded_image_proof':loading_proof} if rule_version==STABILITY_VERSION else {}),
            **({'paint_noise_proof':paint_noise_proof} if paint_noise_proof else {}),'pixel_change':pixel_change}


def validate_capture_receipt(state,receipt,png):
    """Validate v2 from preserved bytes, retaining frozen v1's strict DOM rule."""
    attempt=receipt['attempts'][-1]
    if receipt.get('snapshot_source')!='browser_dom' or receipt.get('coordinate_space')!='screenshot_css_pixels':
        raise ValueError('缺少浏览器同步坐标来源')
    if receipt.get('screenshot_sha256')!=hashlib.sha256(png).hexdigest():raise ValueError('原图与收据不匹配')
    version=receipt.get('schema_version')
    if version is None and 'capture_readiness' not in state:
        if not (attempt.get('dom_stable') is True and attempt.get('before_fingerprint')==fingerprint(state)==attempt.get('after_fingerprint')):
            raise ValueError('旧收据缺少完整DOM稳定证明')
        return True
    if version!=CAPTURE_VERSION:raise ValueError('未知或降级的capture收据版本')
    middle,final=attempt['snapshot_after'],attempt['snapshot_final']
    other=base64.b64decode(attempt['comparison_png_base64'],validate=True)
    if attempt.get('snapshot_before')!=state or base64.b64decode(attempt['original_png_base64'],validate=True)!=png:
        raise ValueError('完整原图/原状态与capture证明不同')
    first_proof=stability_pair(state,middle,png,other,rule_version=attempt['stability']['schema_version'],allow_border=attempt['stability'].get('border_enabled',False),action_scope=attempt['stability'].get('action_scope'))
    last_proof=stability_pair(state,final,png,other,rule_version=attempt['final_stability']['schema_version'],allow_border=attempt['final_stability'].get('border_enabled',False),action_scope=attempt['final_stability'].get('action_scope'))
    if (not first_proof['accepted'] or not last_proof['accepted'] or attempt.get('stability')!=first_proof
            or attempt.get('final_stability')!=last_proof or attempt.get('before_fingerprint')!=fingerprint(state)
            or attempt.get('after_fingerprint')!=fingerprint(final)
            or attempt.get('dom_stable')!=(first_proof['full_dom_stable'] and last_proof['full_dom_stable'])):
        raise ValueError('相关稳态证明与完整原图/状态不一致')
    return True


async def observe(page, selector=None, index=0, timeout=15, assertions=None, protected_selectors=None):
    """A stalled page must reject its task, never stall the entire batch."""
    try:
        options={'selector':selector,'index':index}
        if assertions:options['assertions']=assertions
        if protected_selectors:options['protected_selectors']=protected_selectors
        try:
            return await asyncio.wait_for(page.evaluate(SNAPSHOT_JS,options),timeout=timeout)
        except Exception as error:
            if 'DOCUMENT_NOT_READY' not in str(error) and 'Execution context was destroyed' not in str(error):
                raise
            # Read-only recovery: never replay a navigation or action.
            await page.wait_for_function('document.body && document.readyState !== "loading"', timeout=timeout*1000)
            return await asyncio.wait_for(page.evaluate(SNAPSHOT_JS,options),timeout=timeout)
    except asyncio.TimeoutError as error:
        raise TimeoutError(f'页面同步观察超过{timeout}秒，停止该任务并保留检查点') from error


async def viewport_png(page):
    """Capture actual rendered pixels even if an optional web font never settles."""
    try:
        return await page.screenshot(full_page=False,scale='css',timeout=15000),{'method':'playwright_viewport'}
    except Exception as error:
        # Chrome already renders its fallback font while a remote font request
        # remains pending. CDP reads that real surface without editing the DOM,
        # changing font CSS, intercepting requests or fabricating image pixels.
        if 'waiting for fonts to load' not in str(error):raise
        # Keep the read-only session until page/context closure. Detaching an
        # auxiliary CDP session can reset Chrome target emulation/viewport.
        session=_SCREENSHOT_SESSIONS.get(page)
        if session is None:
            session=await page.context.new_cdp_session(page)
            _SCREENSHOT_SESSIONS[page]=session
        metrics=await page.evaluate('({width:innerWidth,height:innerHeight,deviceScaleFactor:devicePixelRatio,mobile:false})')
        # Auxiliary CDP sessions do not inherit Playwright's per-session device
        # metrics. Reassert the SAME observed configuration, never a crop/layout
        # chosen to improve language or quality scores.
        await session.send('Emulation.setDeviceMetricsOverride',metrics)
        viewport=await page.evaluate('({x:scrollX,y:scrollY,width:innerWidth,height:innerHeight,scale:1/devicePixelRatio})')
        result=await session.send('Page.captureScreenshot',{'format':'png','fromSurface':True,'captureBeyondViewport':False,'clip':viewport})
        return base64.b64decode(result['data'],validate=True),{'method':'chrome_rendered_viewport','font_wait_error':str(error),'device_metrics_reasserted':metrics,'font_rendering_policy':'actual browser fallback; no page content or resource modification'}


async def _capture(page, selector=None, index=0, retries=8, assertions=None, protected_selectors=None,
                   timeout=15, action_scope=None):
    """Capture full original evidence with shared bounded dynamic-region comparison.

    retries remains the total number of attempts, including when explicitly
    supplied. The backoff requests at most eight seconds of sleep in total;
    screenshot/observation timeouts remain independent and unchanged.
    """
    attempts=[]
    delay_before=0.0
    requested_wait=0.0
    observed_wait=0.0
    recent_capture_ms=0.0
    for attempt_index in range(retries):
        if delay_before:
            wait_started=time.monotonic()
            await asyncio.sleep(delay_before)
            observed_wait+=time.monotonic()-wait_started
            requested_wait+=delay_before
        # Classification-based comparison replaces waiting for a global still window.
        native_window={'status':'dynamic_region_comparison','requested_wait_ms':0,'observed_wait_ms':0,'observations':[]}
        pulse=False
        png_waits=[]
        async def timed_png():
            nonlocal requested_wait, observed_wait
            if pulse:
                wait=await _wait_for_native_window(page,max(0,(_CAPTURE_WAIT_BUDGET-requested_wait)*1000),150,png_phase=True)
                png_waits.append(wait)
                requested_wait+=wait['requested_wait_ms']/1000
                observed_wait+=wait['observed_wait_ms']/1000
            return await asyncio.wait_for(viewport_png(page),timeout=25)
        started=time.time_ns()
        options={**({'assertions':assertions} if assertions else {}),
                 **({'protected_selectors':protected_selectors} if protected_selectors else {}),
                 'timeout': timeout}
        before=await observe(page,selector,index,**options)
        try:png,screenshot_evidence=await timed_png()
        except asyncio.TimeoutError as error:raise TimeoutError('视口截图超过25秒，停止该任务并保留检查点') from error
        after=await observe(page,selector,index,**options)
        extra={};v2='capture_readiness' in before
        if v2:
            comparison,comparison_method=await timed_png()
            final=await observe(page,selector,index,**options)
            stability=stability_pair(before,after,png,comparison,allow_border=attempt_index>0,action_scope=action_scope)
            final_stability=stability_pair(before,final,png,comparison,allow_border=attempt_index>0,action_scope=action_scope)
            extra={'snapshot_before':before,'snapshot_after':after,'snapshot_final':final,
                   'original_png_base64':base64.b64encode(png).decode('ascii'),
                   'comparison_png_base64':base64.b64encode(comparison).decode('ascii'),
                   'comparison_screenshot':comparison_method,'stability':stability,'final_stability':final_stability}
        ended=time.time_ns()
        recent_capture_ms=(ended-started)/1e6
        before_fingerprint=fingerprint(before)
        after_fingerprint=fingerprint(after)
        same=before_fingerprint==after_fingerprint
        if v2:same=same and before_fingerprint==fingerprint(final)
        accepted=(stability['accepted'] and final_stability['accepted']) if v2 else same
        next_delay=0.0
        if not accepted and attempt_index+1<retries:
            next_delay=min(_CAPTURE_RETRY_DELAYS[min(attempt_index,len(_CAPTURE_RETRY_DELAYS)-1)],
                           max(0.0,_CAPTURE_WAIT_BUDGET-requested_wait))
        attempts.append({'attempt':attempt_index+1,'started_ns':started,'ended_ns':ended,'dom_stable':same,
                         'delay_before_ms':round(delay_before*1000),'next_retry_delay_ms':round(next_delay*1000),
                         'native_window_wait_ms':round(native_window['requested_wait_ms'],3),
                         'native_window_evidence':native_window,
                         **({'png_phase_waits':png_waits} if png_waits else {}),
                         'mismatch_fields':[key for key in sorted(before.keys()|after.keys())
                                            if key not in before or key not in after or before[key]!=after[key]
                                            or v2 and before.get(key)!=final.get(key)],
                         'before_fingerprint':before_fingerprint,'after_fingerprint':fingerprint(final) if v2 else after_fingerprint,
                         **extra})
        if accepted:
            with Image.open(BytesIO(png)) as im:
                if list(im.size)!=before['screen_resolution']:
                    raise ValueError('截图像素分辨率与 DOM 坐标系不一致')
            if v2:_CAPTURE_FRAMES[page]={'state':before,'png':png,'border_enabled':attempt_index>0,'png_phase':pulse,'action_scope':action_scope}
            return {'state':before,'png':png,'capture':{**({'schema_version':CAPTURE_VERSION} if v2 else {}),
                    'attempts':attempts,'screenshot_sha256':hashlib.sha256(png).hexdigest(),
                    'natural_wait_requested_ms':round(requested_wait*1000),
                    'natural_wait_observed_ms':round(observed_wait*1000),'natural_wait_budget_ms':8000,
                    'coordinate_space':'screenshot_css_pixels','snapshot_source':'browser_dom',
                    'screenshot':screenshot_evidence,
                    'observer_sha256':hashlib.sha256(SNAPSHOT_JS.encode()).hexdigest()}}
        delay_before=next_delay
    error=EvidenceStale('单帧取证期间未能确认截图与界面树同步，拒绝保存该帧')
    # Rejected evidence remains rejected. Callers may preserve this diagnostic
    # alongside their failure checkpoint without treating any PNG as accepted.
    error.capture={'comparison_scope':'single_frame','accepted_as_formal_frame':False,
                   'attempts':attempts,'natural_wait_requested_ms':round(requested_wait*1000),
                   'natural_wait_observed_ms':round(observed_wait*1000),'natural_wait_budget_ms':8000}
    raise error


class SnapshotFault(ValueError):
    responsibility = 'collector'


async def capture(page, selector=None, index=0, retries=8, assertions=None, protected_selectors=None,
                  timeout=15, action_scope=None):
    try:
        return await _capture(page, selector, index, retries, assertions, protected_selectors, timeout=timeout, action_scope=action_scope)
    except Exception as error:
        # Preserve the exact comparison on EvidenceStale. A script exception may
        # precede any tree; retain the available PNG without claiming synchrony.
        if getattr(error, 'capture', None) is not None:
            raise
        diagnostic = {'schema_version': 'webcollect-capture-exception-1',
                      'accepted_as_formal_frame': False, 'action_executed': False,
                      'error_type': type(error).__name__, 'error_message': str(error)}
        try:
            png, method = await asyncio.wait_for(viewport_png(page), timeout=25)
            diagnostic.update(diagnostic_png_base64=base64.b64encode(png).decode('ascii'), screenshot=method)
        except Exception as secondary:
            diagnostic['diagnostic_error_type'] = type(secondary).__name__
        # Only a known observer program error is a proven collector fault.
        if 'ReferenceError:' in str(error) or 'SyntaxError:' in str(error):
            fault = SnapshotFault(str(error)); fault.capture = diagnostic
            raise fault from error
        error.capture = diagnostic
        raise


_PREVERIFY_RETRY_DELAYS=(0.25,0.5)


async def verify_execution_state(page, state, selector=None, index=0, assertions=None, protected_selectors=None,
                                 timeout=15, action_scope=None):
    """Reject any changed captured state before dispatch, including non-control actions.

    Nothing has been dispatched here, so a transient paint mismatch may be
    resolved by a bounded re-observation: re-verify a limited number of times,
    escalating the border tolerance exactly like the capture retry path. A
    changed DOM fingerprint is a real state change and never retried. Every
    failed proof is retained; an accepted re-verification records the rejections
    it superseded. No action is ever replayed by this function.
    """
    options={'assertions':assertions,'timeout':timeout,
             **({'protected_selectors':protected_selectors} if protected_selectors else {})}
    live=await observe(page,selector,index,**options)
    if 'capture_readiness' in state:
        captured=_CAPTURE_FRAMES.get(page)
        if not captured or captured['state']!=state:raise ValueError('派发缺少本次原始capture像素绑定')
        if captured.get('action_scope') != action_scope:
            raise ValueError('Scoped action proof was lost or changed before dispatch')
        rejections=[]
        delays=iter(_PREVERIFY_RETRY_DELAYS)
        phase_budget_ms=3000
        while True:
            phase_wait=None
            if captured.get('png_phase'):
                phase_wait=await _wait_for_native_window(page,phase_budget_ms,150,png_phase=True)
                phase_budget_ms=max(0,phase_budget_ms-phase_wait['requested_wait_ms'])
            png,method=await asyncio.wait_for(viewport_png(page),timeout=25)
            final=await observe(page,selector,index,**options)
            allow_border=captured.get('border_enabled',False) or bool(rejections)
            proof=stability_pair(state,live,captured['png'],png,allow_border=allow_border,action_scope=action_scope)
            final_proof=stability_pair(state,final,captured['png'],png,allow_border=allow_border,action_scope=action_scope)
            if proof['accepted'] and final_proof['accepted']:
                return {'matched':True,'full_state_matched':proof['full_dom_stable'] and final_proof['full_dom_stable'],
                        'state_fingerprint':fingerprint(state),'live_state_fingerprint':fingerprint(live),
                        'final_state_fingerprint':fingerprint(final),'target':live.get('target'),'stability':proof,'final_stability':final_proof,
                        'live_state':live,'final_state':final,'png_base64':base64.b64encode(png).decode('ascii'),'screenshot':method,
                        **({'png_phase_wait':phase_wait} if phase_wait else {}),
                        **({'superseded_rejections':rejections} if rejections else {})}
            rejections.append({'schema_version':'webcollect-execution-state-rejection-1',
                'snapshot_before':state,'snapshot_live':live,'snapshot_final':final,
                'allow_border':allow_border,
                'original_png_base64':base64.b64encode(captured['png']).decode('ascii'),
                'comparison_png_base64':base64.b64encode(png).decode('ascii'),
                'comparison_screenshot':method,'stability':proof,'final_stability':final_proof,
                'accepted_as_formal_frame':False,'action_executed':False,
                'mismatch_fields':[key for key in sorted(state.keys()|live.keys()|final.keys())
                                   if state.get(key)!=live.get(key) or state.get(key)!=final.get(key)]})
            # A changed DOM fingerprint means the planned state itself is gone;
            # only pixel-only mismatches may resolve through re-observation.
            dom_changed=not (proof['related_dom_stable'] and final_proof['related_dom_stable'])
            delay=next(delays,None)
            if dom_changed or delay is None:
                error=EvidenceStale('截图后相关状态或像素发生变化，拒绝用陈旧坐标或终态执行')
                # The later failure screenshot cannot explain this exact rejection.
                # Reuse the collector's existing capture_failure companion to retain
                # the rejected comparison, without replacing the original step PNG.
                error.capture={'schema_version':'webcollect-execution-state-rejection-1',
                    'snapshot_before':state,'snapshot_live':live,'snapshot_final':final,
                    'allow_border':allow_border,
                    'original_png_base64':base64.b64encode(captured['png']).decode('ascii'),
                    'comparison_png_base64':base64.b64encode(png).decode('ascii'),
                    'comparison_screenshot':method,'stability':proof,'final_stability':final_proof,
                    'accepted_as_formal_frame':False,'action_executed':False,
                    'rejections':rejections,
                    'mismatch_fields':[key for key in sorted(state.keys()|live.keys()|final.keys())
                                       if state.get(key)!=live.get(key) or state.get(key)!=final.get(key)]}
                raise error
            await asyncio.sleep(delay)
            live=await observe(page,selector,index,**options)
    if fingerprint(live)!=fingerprint(state):
        changed=[key for key in sorted(live.keys()|state.keys()) if live.get(key)!=state.get(key)]
        raise EvidenceStale('截图后页面状态发生变化，拒绝用陈旧坐标或终态执行：'+','.join(changed))
    return {'matched':True,'state_fingerprint':fingerprint(live),'target':live.get('target')}


def prepare_action(state, operation):
    from .agent_observation import require_action
    require_action(state, operation)
    action=operation['action_type']
    target=state['target']
    parameters=dict(operation.get('arguments',{}))
    element=None
    if action in CONTROL:
        if not target:raise PlanViewportInfeasible('目标未出现在当前视口界面树；必须先显式滚动')
        element=next(e for e in state['elements'] if e['element_id']==target['element_id'])
        if not element['enabled']:raise ValueError('目标控件不可用')
        visual_kind=(operation.get('evidence') or {}).get('target_visual_kind','text')
        if visual_kind!='text':
            from .html_table_strategy import validate_visual_target
            validate_visual_target(state,operation)
        expected_label=(operation.get('evidence') or {}).get('target_label')
        if expected_label:
            import re
            compact=lambda text:re.sub(r'\s+','',text)
            labels=target.get('visible_label_evidence',[])
            if not any(compact(expected_label) in compact(row.get('text','')) for row in labels):
                raise PlanLabelUnreadable('M4_TARGET_LABEL_UNREADABLE: 目标文字未完整可读；可命中裁切框或无障碍名称不能代替可见标签')
        if action in POINTER:
            if not target['hit_valid']:raise ValueError('目标中心被其他元素遮挡')
            parameters.update(x=target['coordinate'][0],y=target['coordinate'][1])
        if action=='type' and (not target['focused'] or not element['inputable']):
            raise ValueError('type 仅对当前已聚焦的输入控件执行；请先显式点击')
        if action=='type':
            value=next((v for v in state.get('values',[]) if v['element_id']==element['element_id']),{})
            if value.get('input_type') in {'date','time','month','week','datetime-local'}:
                raise ValueError('原生日期时间控件不支持统一 type 的 insert_text 语义；请规划显式按键操作，不以 fill 替代')
    if action=='scroll':
        parameters.setdefault('x',state['screen_resolution'][0]//2)
        parameters.setdefault('y',state['screen_resolution'][1]//2)
    from .validate import StrictValidator, SCHEMAS
    schema=json.loads(SCHEMAS.joinpath('annotation.schema.json').read_text())['properties']['steps']['items']['properties']['tool_call']
    call={'tool_name':action,'call_id':'validation','arguments':parameters,'timestamp':'','context':'Web'}
    errors=list(StrictValidator(schema).iter_errors(call))
    if errors:raise ValueError('执行前统一动作参数不合法：'+errors[0].message)
    width,height=state['screen_resolution']
    for xkey,ykey in [('x','y'),('end_x','end_y')]:
        if xkey in parameters and not (0<=parameters[xkey]<width and 0<=parameters[ykey]<height):
            raise ValueError('执行前发现坐标越界')
        if xkey in parameters and any(frame['bbox'][0]<=parameters[xkey]<frame['bbox'][2] and
            frame['bbox'][1]<=parameters[ykey]<frame['bbox'][3] for frame in state.get('embedded_frames',[])):
            raise ValueError('UNSUPPORTED_FRAME: 动作坐标落在未读取子树的嵌入框内，拒绝执行')
    if action=='hotkey' and any(frame.get('focused') for frame in state.get('embedded_frames',[])):
        raise ValueError('UNSUPPORTED_FRAME: 当前焦点位于嵌入框内，不能向未知子树派发按键')
    return parameters,element


async def _execute_action(page, action, args, execution=None):
    execution=execution or {}
    if action in {'click','double_click','right_click'}:
        await page.mouse.click(args['x'],args['y'],click_count=2 if action=='double_click' else 1,
                               button='right' if action=='right_click' else 'left')
    elif action=='type':
        native_type=await page.evaluate('document.activeElement?.type')
        if native_type in {'date','time','month','week','datetime-local'}:
            raise ValueError('原生日期时间控件不支持统一 type 的 insert_text 语义，不以 fill 替代')
        else:await page.keyboard.insert_text(args['text'])
    elif action=='hotkey':
        keymap={'meta':'Meta','command':'Meta','cmd':'Meta','⌘':'Meta',
                'ctrl':'Control','control':'Control','ctl':'Control','alt':'Alt','option':'Alt','opt':'Alt','⌥':'Alt',
                'shift':'Shift','win':'Meta','windows':'Meta','super':'Meta','enter':'Enter','return':'Enter',
                'escape':'Escape','esc':'Escape','tab':'Tab','backspace':'Backspace','delete':'Delete','del':'Delete',
                'insert':'Insert','ins':'Insert','space':'Space','spacebar':'Space','home':'Home','end':'End',
                'pageup':'PageUp','pgup':'PageUp','pagedown':'PageDown','pgdn':'PageDown',
                'arrowdown':'ArrowDown','down':'ArrowDown','arrowup':'ArrowUp','up':'ArrowUp',
                'arrowleft':'ArrowLeft','left':'ArrowLeft','arrowright':'ArrowRight','right':'ArrowRight',
                'capslock':'CapsLock','numlock':'NumLock','scrolllock':'ScrollLock','pause':'Pause',
                'printscreen':'PrintScreen','contextmenu':'ContextMenu'}
        def native_key(key):
            if key.lower().startswith('f') and key[1:].isdigit() and 1<=int(key[1:])<=24:
                return 'F'+str(int(key[1:]))
            return keymap.get(key.lower(),key)
        await page.keyboard.press('+'.join(native_key(key) for key in args['keys']))
    elif action=='scroll':
        distance=execution.get('distance',480)
        if type(distance) is not int or distance<=0:raise ValueError('滚动距离须为正整数')
        dx,dy={'up':(0,-distance),'down':(0,distance),'left':(-distance,0),'right':(distance,0)}[args['direction']]
        await page.mouse.move(args['x'],args['y'])
        await page.mouse.wheel(dx,dy)
    elif action=='drag':
        await page.mouse.move(args['x'],args['y']);await page.mouse.down()
        await page.mouse.move(args['end_x'],args['end_y'],steps=execution.get('steps',10));await page.mouse.up()
    elif action=='select':
        handle=await page.evaluate_handle('({x,y})=>document.elementFromPoint(x,y)',args)
        element=handle.as_element()
        if not element or await element.evaluate('(node)=>node.tagName')!='SELECT':
            raise ValueError('select 只映射到当前坐标命中的可见原生 select')
        # Unified select is an atomic primitive. It emits real input/change events
        # on the observed native control without inventing an unobserved popup.
        await element.select_option(label=args['option'])
    elif action=='back':await page.go_back(wait_until='domcontentloaded')
    elif action=='open_url':await page.goto(args['url'],wait_until='domcontentloaded')
    elif action=='wait':await page.wait_for_timeout(execution.get('duration_ms',1000))
    elif action=='complete':return
    else:raise ValueError('不支持的 Web 动作 '+action)


async def execute(page, action, args, execution=None):
    execution=execution or {}
    if execution.get('wait_navigation'):
        # Mouse/keyboard APIs do not wait for document navigation. Register the
        # observer before dispatch so assertions never read the departing page.
        async with page.expect_navigation(wait_until='domcontentloaded',timeout=15000):
            await _execute_action(page,action,args,execution)
    else:
        await _execute_action(page,action,args,execution)
    if action!='complete':
        await page.wait_for_timeout(execution.get('settle_ms',500))
