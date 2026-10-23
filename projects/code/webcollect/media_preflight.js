/* Read-only media/timing facts. Never play/pause, rewrite DOM/CSS, or fetch. */
({targets = []} = {}) => {
  const clean=value=>String(value||'').replace(/\s+/g,' ').trim();
  const safe=value=>{
    if(typeof value==='number'&&!Number.isFinite(value))return String(value);
    if(Array.isArray(value))return value.map(safe);
    if(value&&typeof value==='object')return Object.fromEntries(Object.entries(value).map(([key,item])=>[key,safe(item)]));
    return value;
  };
  const selector=node=>{
    if(node.id){const id='#'+CSS.escape(node.id);if(document.querySelectorAll(id).length===1)return id;}
    const parts=[];
    for(let n=node;n&&n.nodeType===1;n=n.parentElement){
      const siblings=n.parentElement?[...n.parentElement.children].filter(s=>s.localName===n.localName):[n];
      parts.unshift(n.localName+':nth-of-type('+(siblings.indexOf(n)+1)+')');
      if(document.querySelectorAll(parts.join(' > ')).length===1)return parts.join(' > ');
    }
    return parts.join(' > ');
  };
  const rect=node=>{const r=node.getBoundingClientRect();return {x:r.x,y:r.y,width:r.width,height:r.height};};
  const box=r=>[Math.max(0,r.x),Math.max(0,r.y),Math.min(innerWidth,r.x+r.width),Math.min(innerHeight,r.y+r.height)];
  const visible=node=>{
    if(!(node instanceof Element)||!node.isConnected)return false;
    for(let n=node;n;n=n.parentElement){const s=getComputedStyle(n);if(s.display==='none'||s.visibility!=='visible'||Number(s.opacity)===0)return false;}
    const r=node.getBoundingClientRect();return r.width>0&&r.height>0&&r.right>0&&r.bottom>0&&r.left<innerWidth&&r.top<innerHeight;
  };
  const points=node=>{
    const b=box(rect(node));if(b[2]<=b[0]||b[3]<=b[1])return [];
    return [[.5,.5],[.15,.5],[.85,.5],[.5,.15],[.5,.85]].map(([x,y])=>[b[0]+(b[2]-b[0])*x,b[1]+(b[3]-b[1])*y]);
  };
  const hitFacts=node=>points(node).map(([x,y])=>{const hit=document.elementFromPoint(x,y);return {point:[x,y],hit_selector:hit?selector(hit):null,
    related_to_node:!!hit&&(hit===node||node.contains(hit)||hit.contains(node))};});
  const overlaps=(a,b)=>Math.min(a[2],b[2])>Math.max(a[0],b[0])&&Math.min(a[3],b[3])>Math.max(a[1],b[1]);
  const targetNodes=[],taskTargets=[];
  for(const taskTarget of targets){
    let node=null,error=null;try{node=document.querySelectorAll(taskTarget.selector)[taskTarget.index||0]||null;}catch(e){error=String(e);}
    const hits=node&&visible(node)?hitFacts(node):[];
    taskTargets.push({...taskTarget,found:!!node,style_viewport_visible:!!node&&visible(node),bbox:node?box(rect(node)):null,
      visible_hit:hits.some(h=>h.related_to_node),hit_samples:hits,selector_error:error});
    targetNodes.push(node);
  }
  const adLabel=/^(?:广告|推广|赞助|广告推广|Advertisement|Sponsored|Promotion)$/i;
  const labelledPromotion=/^(?:广告|推广|赞助|广告推广|Advertisement|Sponsored|Promotion)(?:\s*[:：]\s*.{1,120})?$/i;
  const context=node=>{
    const region=node.closest('article,[itemprop="articleBody"],[role="main"],main');
    const heading=region?.querySelector('h1,h2,[role="heading"]');
    const figure=node.closest('figure');const caption=figure?.querySelector('figcaption');
    const markers=[];
    const marked=node.closest('[data-ad],[data-ad-slot],[data-ad-client]');
    if(marked)markers.push({kind:'explicit_ad_attribute',selector:selector(marked),attributes:[...marked.attributes].filter(a=>/^data-ad(?:$|-)/.test(a.name)).map(a=>({name:a.name,value:a.value}))});
    for(let owner=node,depth=0;owner&&depth<3;owner=owner.parentElement,depth++){
      for(const name of ['aria-label','title'])if(labelledPromotion.test(clean(owner.getAttribute(name))))markers.push({kind:'explicit_ad_label',selector:selector(owner),attribute:name,text:clean(owner.getAttribute(name))});
      for(const label of owner.children){
        if(label.matches('span,small,label,[role="note"]')&&visible(label)&&adLabel.test(clean(label.textContent))&&hitFacts(label).some(h=>h.related_to_node))
          markers.push({kind:'rendered_ad_marker',selector:selector(label),text:clean(label.textContent)});
      }
    }
    // A media tag, autoplay, aside or article about advertising is never an ad
    // label. Retain explicit evidence; the summary calls it a candidate only.
    return {article_region_selector:region?selector(region):null,
      heading:heading&&visible(heading)?clean(heading.textContent).slice(0,300):'',
      caption:caption&&visible(caption)?clean(caption.textContent).slice(0,400):'',
      explicit_ad_markers:markers};
  };
  const advertisingMarkers=[];let markerTruncated=false;
  for(const node of document.querySelectorAll('[data-ad],[data-ad-slot],[data-ad-client],[aria-label],[title],span,small,label,[role="note"],[role="dialog"] h1,[role="dialog"] h2')){
    if(!visible(node))continue;
    let kind=null,text='',attribute=null;
    if(node.matches('[data-ad],[data-ad-slot],[data-ad-client]'))kind='explicit_ad_attribute';
    for(const name of ['aria-label','title'])if(labelledPromotion.test(clean(node.getAttribute(name)))){kind='explicit_ad_label';text=clean(node.getAttribute(name));attribute=name;}
    if((node.matches('span,small,label,[role="note"]')&&adLabel.test(clean(node.textContent)))||
       (node.matches('[role="dialog"] h1,[role="dialog"] h2')&&labelledPromotion.test(clean(node.textContent)))){kind='rendered_ad_marker';text=clean(node.textContent);}
    if(!kind)continue;if(advertisingMarkers.length>=100){markerTruncated=true;break;}
    advertisingMarkers.push({kind,selector:selector(node),text,attribute,bbox:box(rect(node)),hit_samples:hitFacts(node),
      attributes:kind==='explicit_ad_attribute'?[...node.attributes].filter(a=>/^data-ad(?:$|-)/.test(a.name)).map(a=>({name:a.name,value:a.value})):[]});
  }
  const facts=node=>{
    const b=box(rect(node));return {selector:selector(node),tag:node.localName,bbox:b,rect:rect(node),
      style_viewport_visible:true,hit_samples:hitFacts(node),context:context(node),
      task_relations:targetNodes.map((target,index)=>{
        const overlap=!!target&&overlaps(b,box(rect(target)));
        const contains=!!target&&(node===target||node.contains(target));
        const inside=!!target&&target.contains(node);
        const covers=!!target&&!contains&&!inside&&taskTargets[index].style_viewport_visible&&points(target).some(([x,y])=>{
          const hit=document.elementFromPoint(x,y);return !!hit&&(hit===node||node.contains(hit));});
        return {operation_index:taskTargets[index].operation_index,target_selector:taskTargets[index].selector,
          geometry_overlaps:overlap,contains_target:contains,inside_target:inside,dom_hit_covers_target_point:covers};
      })};
  };
  const media=[],native=[];let mediaTruncated=false,animationTruncated=false;
  for(const node of document.querySelectorAll('video,iframe,canvas,svg image,img')){
    if(!visible(node))continue;if(media.length>=250){mediaTruncated=true;break;}
    const base=facts(node);let item;
    if(node.localName==='video')item={...base,kind:'video',paused:node.paused,current_time:node.currentTime,ready_state:node.readyState,
      autoplay:node.autoplay,muted:node.muted,ended:node.ended,playback_rate:node.playbackRate,duration:node.duration,
      current_src:node.currentSrc,source_attribute:node.getAttribute('src')||'',poster:node.poster,video_width:node.videoWidth,video_height:node.videoHeight,
      source_object_present:!!node.srcObject,playing_is_not_observed_time_progress:true};
    else if(node.localName==='iframe'){
      let crossOrigin=null;try{if(node.src&&!node.src.startsWith('about:'))crossOrigin=new URL(node.src,location.href).origin!==location.origin;}catch(_){}
      item={...base,kind:'iframe',src:node.getAttribute('src')||'',srcdoc_present:node.hasAttribute('srcdoc'),cross_origin:crossOrigin,
        internal_content:'UNKNOWN_NOT_INSPECTED',dynamic_content:'UNKNOWN'};
    }else if(node.localName==='canvas')item={...base,kind:'canvas',dynamic_content:'UNKNOWN_NO_PIXEL_OR_SCRIPT_INSPECTION'};
    else if(node.localName==='image')item={...base,kind:'svg_image',source:node.href?.baseVal||'',dynamic_content:'UNKNOWN'};
    else{const source=node.currentSrc||node.src||'';item={...base,kind:'image_candidate',source,alt:node.alt||'',
      gif_url_candidate:/\.gif(?:$|[?#])/i.test(source),dynamic_content:'UNKNOWN_IMAGE_PRESENCE_DOES_NOT_PROVE_ANIMATION'};}
    if(item.kind==='video'&&node.srcObject){
      item.source_object_id=node.srcObject.id||null;
      item.source_object_tracks=typeof node.srcObject.getTracks==='function'?node.srcObject.getTracks().map(track=>({id:track.id,kind:track.kind,ready_state:track.readyState})):null;
    }
    media.push(safe(item));
  }
  for(const animation of document.getAnimations()){
    const effect=animation.effect,node=effect?.target;if(!visible(node))continue;
    if(native.length>=100){animationTruncated=true;break;}
    native.push(safe({...facts(node),kind:animation.constructor.name,play_state:animation.playState,pending:animation.pending,
      current_time:animation.currentTime,playback_rate:animation.playbackRate,start_time:animation.startTime,
      timing:effect.getTiming(),computed_timing:effect.getComputedTiming(),composite:effect.composite,
      iteration_composite:effect.iterationComposite,pseudo_element:effect.pseudoElement||null,keyframes:effect.getKeyframes(),
      target:{tag:node.localName,id:node.id,rect:rect(node)}}));
  }
  return {schema_version:'media-preflight-probe-1',page_url:location.href,title:document.title,
    document_identity:{url_without_fragment:location.href.split('#')[0],performance_time_origin:performance.timeOrigin},
    observed_at_performance_ms:performance.now(),viewport:{width:innerWidth,height:innerHeight,scroll_x:scrollX,scroll_y:scrollY},
    task_targets:taskTargets,media,native_animations:native,explicit_ad_markers:advertisingMarkers,read_only:true,
    limitations:{style_viewport_intersection_is_not_full_occlusion_proof:true,hit_samples_are_DOM_facts_not_visual_QC:true,
      iframe_internals_not_inspected:true,decoded_video_GIF_canvas_pixels_not_inspected:true,
      finite_observation_never_proves_permanent_static:true,media_truncated:mediaTruncated,animations_truncated:animationTruncated,ad_markers_truncated:markerTruncated}};
}
