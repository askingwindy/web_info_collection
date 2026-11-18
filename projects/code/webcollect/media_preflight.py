"""Read-only media triage. Routes schedule work; none certifies quality."""
import asyncio
import hashlib
from webcollect import workspace_json as json
from importlib.resources import files
import math
from urllib.parse import urldefrag

from .browser import STABILITY_VERSION as BROWSER_STABILITY_RULE, _native_animation_window

MEDIA_JS=files('webcollect').joinpath('media_preflight.js').read_text(encoding='utf-8')
OBSERVER_SHA256=hashlib.sha256(MEDIA_JS.encode()).hexdigest()
ALGORITHM_VERSION='media-preflight-dynamic-regions'
ROUTES={'NORMAL_M1','PREPARE_RECHECK','DYNAMIC_CONTENT_TRACK','REVIEW_REQUIRED'}


def task_media_targets(task):
    """Protect operation targets and result selectors, including intermediate results."""
    targets=[]
    for index,operation in enumerate(task.get('operations',[])[:50]):
        if operation.get('selector'):
            targets.append({'operation_index':index,'action_type':operation.get('action_type'),
                            'selector':operation['selector'],'index':operation.get('index',0)})
        for condition in operation.get('postconditions',[]):
            if condition.get('selector'):
                targets.append({'operation_index':index,'action_type':'postcondition',
                                'selector':condition['selector'],'index':condition.get('index',0)})
    for condition in task.get('final_assertions',[]):
        if condition.get('selector'):
            targets.append({'operation_index':None,'action_type':'final_assertion',
                            'selector':condition['selector'],'index':condition.get('index',0)})
    return targets


async def probe_media(page,task,timeout=10):
    """Record browser facts without actions, resource requests or media control."""
    targets=task_media_targets(task)
    try:result=await asyncio.wait_for(page.evaluate(MEDIA_JS,{'targets':targets}),timeout=timeout)
    except asyncio.TimeoutError as error:raise TimeoutError('只读媒体预检超过时限；不能视为无动态风险') from error
    if len(task.get('operations',[]))>50:
        result.setdefault('limitations',{})['task_targets_truncated']=True
    result.update(observer_sha256=OBSERVER_SHA256,algorithm_version=ALGORITHM_VERSION)
    return result


def _number(value):
    return type(value) in (int,float) and math.isfinite(value)


def _bbox(value):
    if isinstance(value,dict):
        if all(_number(value.get(k)) for k in ['x','y','width','height']):
            value=[value['x'],value['y'],value['x']+value['width'],value['y']+value['height']]
        else:return None
    if not isinstance(value,(list,tuple)) or len(value)!=4 or not all(_number(v) for v in value):return None
    return list(value) if value[2]>value[0] and value[3]>value[1] else None


def _overlap(first,second):
    return bool(first and second and min(first[2],second[2])>max(first[0],second[0]) and min(first[3],second[3])>max(first[1],second[1]))


def _accepted_image_only_proof(proof):
    # Later capture rules can also accept border or repaint differences. Those
    # pixels cannot be attributed to a background image by this preflight.
    return (isinstance(proof,dict) and proof.get('schema_version') == BROWSER_STABILITY_RULE
            and proof.get('accepted') is True and proof.get('related_dom_stable') is True
            and proof.get('loading_complete') is True
            and not proof.get('border_proof') and not proof.get('paint_noise_proof'))


def _bounded_image_change(change,regions,probes):
    """Do not weaken routing from a flag alone or from aggregate bbox overlap."""
    proof=change.get('related_stability');pairs=change.get('diagnostic_pair_stability')
    from .dynamic_regions import STABILITY as dynamic_rule
    if isinstance(proof,dict) and proof.get('schema_version')==dynamic_rule:
        return bool(proof.get('accepted') and proof.get('loading_complete') and proof.get('allowed_dynamic_regions')
            and proof.get('pixel_change',{}).get('outside_allowed_pixels')==0
            and isinstance(pairs,list) and len(pairs)==2 and all(p.get('schema_version')==dynamic_rule and p.get('accepted') for p in pairs))
    if (not _accepted_image_only_proof(proof) or not isinstance(pairs,list) or len(pairs)!=2
            or not all(_accepted_image_only_proof(pair) and pair['schema_version']==proof['schema_version']
                       for pair in pairs)):
        return False
    pixels=proof.get('pixel_change',{});allowed=proof.get('allowed_image_regions')
    if (type(pixels.get('changed_pixels')) is not int or pixels['changed_pixels']<=0
            or type(pixels.get('outside_allowed_pixels')) is not int or pixels['outside_allowed_pixels']!=0
            or not isinstance(allowed,list) or not allowed):
        return False
    for region in allowed:
        box=_bbox(region.get('bbox')) if isinstance(region,dict) else None
        if not box or not region.get('element_id') or any(_overlap(box,r['bbox']) for r in regions if r['kind']!='body'):
            return False
        # The full snapshot's eligible IMG must also exist in every media probe.
        # Never apply an IMG exception to canvas, iframe or ambiguous target media.
        for probe in probes:
            matches=[item for item in probe.get('media',[]) if item.get('kind')=='image_candidate' and _bbox(item.get('bbox'))==box]
            if len(matches)!=1 or any(any(relation.get(key) for key in (
                    'geometry_overlaps','contains_target','inside_target','dom_hit_covers_target_point'))
                    for relation in matches[0].get('task_relations',[])):
                return False
    return True


def summarize_preflight(probes,assessments,pixel_changes=None):
    """Combine time-ordered observations, keeping inference separate from facts.

    Native timing uses the existing conservative hold planner. Pixel changes
    indicate change only; they never label advertising or certify stability.
    """
    if not isinstance(probes,list) or not isinstance(assessments,list):raise ValueError('probes和assessments必须为按时间排序的列表')
    if pixel_changes is not None and not isinstance(pixel_changes,list):raise ValueError('pixel_changes必须为列表或None')
    latest=probes[-1] if probes else {};assessment=assessments[-1] if assessments else {}
    reasons=[];review=[];dynamic=[];prepare=[];regions=[]
    documents={(p.get('document_identity',{}).get('url_without_fragment',urldefrag(p.get('page_url',''))[0]),
                p.get('document_identity',{}).get('performance_time_origin')) for p in probes}
    if not probes or not assessments:review.append('Missing media or content assessment; task impact is unknown.')
    if len(documents)>1:review.append('Probes span different documents; do not merge their timelines.')
    if any(not p.get('document_identity',{}).get('url_without_fragment') or
           not _number(p.get('document_identity',{}).get('performance_time_origin')) for p in probes):
        review.append('Document identity is missing; timeline continuity is unknown.')
    times=[p.get('observed_at_performance_ms') for p in probes]
    if any(not _number(t) for t in times) or any(b<a for a,b in zip(times,times[1:]) if _number(a) and _number(b)):
        review.append('Probe ordering/timestamps cannot establish time progress.')
    for p in probes:
        if any(p.get('limitations',{}).get(k) for k in ['media_truncated','animations_truncated','ad_markers_truncated','task_targets_truncated']):
            review.append('Candidate inventory is truncated; risk coverage is incomplete.')
    body=assessment.get('body',{})
    if _bbox(body.get('bbox')):regions.append({'kind':'body','selector':body.get('selector'),'bbox':_bbox(body['bbox']),
                                             'readable':body.get('visible',False)})
    for field in assessment.get('reference_content',{}).get('evidence',[]):
        if _bbox(field.get('bbox')):regions.append({'kind':'reference','selector':field.get('selector'),'bbox':_bbox(field['bbox'])})
    for target in latest.get('task_targets',[]):
        if target.get('style_viewport_visible') and _bbox(target.get('bbox')):
            regions.append({'kind':'task_target','selector':target.get('selector'),'operation_index':target.get('operation_index'),
                            'bbox':_bbox(target['bbox']),'visible_hit':target.get('visible_hit')})
    decision=assessment.get('decision',{}).get('action')
    if decision in ['close_overlay','scroll_to_content']:prepare.append('Existing preparation advises a real close/scroll followed by recheck.')
    elif decision=='blocked' or assessment.get('obstruction',{}).get('present'):
        review.append('Current content/target is obstructed or has no verified preparation route.')
    groups={}
    for probe_index,probe in enumerate(probes):
        for item in probe.get('media',[]):groups.setdefault((item.get('kind'),item.get('selector')),[]).append((probe_index,item))
        for item in probe.get('native_animations',[]):groups.setdefault(('native_animation',item.get('selector')),[]).append((probe_index,item))
    evidence=[];capture_risks=[]
    pixel_clues=[]
    for change in pixel_changes or []:
        fraction=change.get('changed_fraction');box=_bbox(change.get('bbox'))
        if _number(fraction) and 0<fraction<=1:
            bounded=_bounded_image_change(change,regions,probes)
            pixel_clues.append({'changed_fraction':fraction,'bbox':box,'only_a_change_clue':True,
                                'critical_geometry_overlap':any(_overlap(box,r['bbox']) for r in regions),
                                'bounded_irrelevant_image_change':bounded,
                                'related_stability':change.get('related_stability')})
            if bounded:reasons.append('Exact pixel differences are confined to proved allowed dynamic regions; task targets and business evidence remain protected; original frames and full states remain evidence.')
    proven_dynamic=[r for change in (pixel_changes or []) if _bounded_image_change(change,regions,probes)
        for r in (change.get('related_stability') or {}).get('allowed_dynamic_regions',[])]
    def within_dynamic(box):
        return bool(box and any(r['bbox'][0]<=box[0] and r['bbox'][1]<=box[1] and r['bbox'][2]>=box[2] and r['bbox'][3]>=box[3] for r in proven_dynamic))
    for (kind,selector),observations in groups.items():
        last=observations[-1][1];context=last.get('context',{});markers=context.get('explicit_ad_markers',[])
        role='promotional_candidate' if markers else 'editorial_candidate' if context.get('article_region_selector') and (context.get('heading') or context.get('caption')) else 'unknown'
        box=_bbox(last.get('bbox'));overlaps=[r for r in regions if _overlap(box,r['bbox'])]
        covers=[r for r in last.get('task_relations',[]) if r.get('dom_hit_covers_target_point')]
        target_content=[r for r in last.get('task_relations',[]) if r.get('contains_target') or r.get('inside_target')]
        related=bool(overlaps or target_content or covers)
        bounded_dynamic=within_dynamic(box)
        row={'kind':kind,'selector':selector,'observed_probe_indices':[i for i,_ in observations],'observation_count':len(observations),
             'media_role':role,'role_is_context_candidate_not_ground_truth':True,'context_evidence':context,
             'bbox':box,'critical_geometry_overlaps':overlaps,'geometry_overlap_does_not_prove_occlusion':True,
             'task_dom_hit_coverage':covers,'task_content_relations':target_content,
             'task_or_body_geometry_related':related,'shared_allowed_dynamic_region':bounded_dynamic,'observed_time_progress':None,
             'time_progress_scope':'video_current_time_only','observations':[]}
        if covers:review.append('Media wins DOM hit samples over a planned target: '+str(selector))
        if kind=='video':
            video_times=[x.get('current_time') for _,x in observations]
            sources={json.dumps({k:x.get(k) for k in ['current_src','source_attribute','source_object_present','source_object_id','source_object_tracks']},sort_keys=True) for _,x in observations}
            reversed_time=any(b<a for a,b in zip(video_times,video_times[1:]) if _number(a) and _number(b))
            continuity=len(sources)==1 and not reversed_time and len(documents)==1
            advanced=continuity and len(video_times)>=2 and all(_number(t) for t in video_times) and any(b>a+.03 for a,b in zip(video_times,video_times[1:]))
            playing=last.get('paused') is False and last.get('ended') is not True
            row.update(observed_time_progress=advanced,playing_state_observed=playing,
                       timeline_source_consistent=continuity,element_identity_across_probes='NOT_PROVEN_BY_SELECTOR',
                       paused=last.get('paused'),ready_state=last.get('ready_state'),autoplay=last.get('autoplay'))
            if not continuity and not bounded_dynamic:review.append('Video source changed or media time reversed; do not join timelines: '+str(selector))
            if advanced or playing:
                capture_risks.append('Playing/video time progress can change pixels: '+str(selector))
                if not bounded_dynamic and (related or role=='editorial_candidate'):dynamic.append('Preserve '+role+' video; playback/time progress needs the dynamic-content track: '+str(selector))
            row['observations']=[{'probe_index':i,**{k:x.get(k) for k in ['paused','current_time','ready_state','autoplay','ended','current_src','source_attribute','source_object_id','source_object_tracks','poster']}} for i,x in observations]
        elif kind=='iframe':
            row.update(internal_content='UNKNOWN_NOT_INSPECTED',cross_origin=last.get('cross_origin'))
            if not bounded_dynamic:review.append('Visible iframe internals are uninspected; never infer editorial/ad content or stability: '+str(selector))
        elif kind in ['canvas','svg_image','image_candidate']:
            local_clues=[c for c in pixel_clues if _overlap(c['bbox'],box)]
            row.update(pixel_change_clues=local_clues,pixel_bbox_is_aggregate_weak_clue=True,
                       rendered_animation='UNKNOWN_WITHOUT_DECODED_CONTENT_INSPECTION',gif_url_candidate=last.get('gif_url_candidate',False))
            if local_clues:capture_risks.append('Aggregate changed-pixel bbox overlaps media; this does not prove that media itself changed: '+str(selector))
            if target_content and not (local_clues and all(c['bounded_irrelevant_image_change'] for c in local_clues)) and (kind in ['canvas','svg_image'] or last.get('gif_url_candidate')):
                review.append('Task targets opaque rendered content whose semantics are uninspected: '+str(selector))
            elif related and any(not clue['bounded_irrelevant_image_change'] for clue in local_clues):
                dynamic.append('Aggregate pixel-change geometry overlaps relevant opaque media; cause is unverified: '+str(selector))
        else:
            row['observations']=[{'probe_index':i,'play_state':x.get('play_state'),'current_time':x.get('current_time')} for i,x in observations]
        evidence.append(row)
    native=latest.get('native_animations',[])
    native_advice=_native_animation_window({'visible_animations':native},8000,1000)
    running_native=any(a.get('play_state')=='running' or a.get('pending') for a in native)
    if running_native and not (pixel_clues and all(c['bounded_irrelevant_image_change'] for c in pixel_clues)) and native_advice['status'] in ['unsupported','no_common_window_within_budget']:
        capture_risks.append('Visible native motion has no jointly proved long hold within the existing capture wait budget.')
        if any(row['kind']=='native_animation' and row['task_or_body_geometry_related'] and not row.get('shared_allowed_dynamic_region') for row in evidence):
            dynamic.append('Native motion intersects task/content geometry and has no jointly proved long hold within the existing capture wait budget.')
        else:reasons.append('Native motion is outside observed task/content geometry; normal M1 remains subject to strict capture checks.')
    elif running_native:reasons.append('Native timing is advisory; versioned region comparison and independent target/business evidence remain mandatory, with original fingerprints retained.')
    if any(c['critical_geometry_overlap'] and not c['bounded_irrelevant_image_change'] for c in pixel_clues) and not dynamic:
        dynamic.append('Temporal pixel changes intersect task/content geometry; cause and advertising role remain unknown.')
    if review:routing='REVIEW_REQUIRED';reasons+=review
    elif prepare:routing='PREPARE_RECHECK';reasons+=prepare
    elif dynamic:routing='DYNAMIC_CONTENT_TRACK';reasons+=dynamic
    else:
        routing='NORMAL_M1';reasons.append('No observed condition requires a different route in this limited probe window; normal capture/QC still required.')
    return {'schema_version':'media-preflight-summary','algorithm_version':ALGORITHM_VERSION,'routing':routing,
            'reasons':list(dict.fromkeys(reasons)),'media_evidence':evidence,'native_window_advice':native_advice,
            'advertising_marker_evidence':[{'probe_index':index,**marker} for index,p in enumerate(probes) for marker in p.get('explicit_ad_markers',[])],
            'critical_regions':regions,'pixel_change_clues':pixel_clues,'other_dynamic_reasons':list(dict.fromkeys(dynamic)),
            'page_capture_risks':list(dict.fromkeys(capture_risks)),
            'probe_count':len(probes),'assessment_count':len(assessments),'document_count':len(documents),
            'observation_limits':{'finite_window_never_proves_permanent_static':True,'pixel_changes_never_prove_advertising':True,
              'editorial_video_is_preserved':True,'predictions_do_not_certify_capture_or_quality':True,
              'no_frame_internal_or_decoded_media_inspection':True},'quality_evaluation':'NOT_PERFORMED','page_actions_performed':0}
