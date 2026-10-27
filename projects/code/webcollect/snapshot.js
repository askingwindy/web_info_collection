/* Read-only visible DOM evidence. No page content, attributes or styles are changed. */
({selector = null, index = 0, assertions = []} = {}) => {
  const width = innerWidth, height = innerHeight;
  const target = selector ? document.querySelectorAll(selector)[index] : null;
  if(target?.matches('iframe,frame'))throw new Error('UNSUPPORTED_FRAME: task targets inside embedded frames require frame-aware execution');
  const records = [], nodes = [];
  const observerKey=Symbol.for('webcollect.observer.v1');
  const observer=globalThis[observerKey] ||= {ids:new WeakMap(),next:1};
  const clean = text => (text || '').replace(/\s+/g, ' ').trim();
  const scaleCache=new WeakMap();
  const axisScale = element => {
    if(!element)return {a:1,b:0,c:0,d:1};
    if(scaleCache.has(element))return scaleCache.get(element);
    const style=getComputedStyle(element),matrix=new DOMMatrixReadOnly(style.transform==='none'?undefined:style.transform);
    const rotation=style.rotate||'none';
    const factors=(style.scale==='none'||!style.scale?[1,1]:style.scale.split(/\s+/).map(Number));
    const sx=factors[0],sy=factors[1]??sx;
    const nearZero=value=>Math.abs(value)<1e-8;
    const local={a:nearZero(matrix.a)?0:matrix.a,b:nearZero(matrix.b)?0:matrix.b,
                 c:nearZero(matrix.c)?0:matrix.c,d:nearZero(matrix.d)?0:matrix.d};
    const diagonal=local.b===0&&local.c===0&&local.a!==0&&local.d!==0;
    const quarterTurn=local.a===0&&local.d===0&&local.b!==0&&local.c!==0;
    if(!matrix.is2D||!(diagonal||quarterTurn)||
       (rotation!=='none'&&!/^0(?:deg|rad|grad|turn)?$/.test(rotation))||
       !Number.isFinite(sx)||!Number.isFinite(sy)||sx===0||sy===0||
       (factors.length>2&&factors[2]!==1)||style.perspective!=='none') {
      throw new Error('UNSUPPORTED_GEOMETRY: non-axis-aligned rotation/skew/perspective cannot supply target truth');
    }
    const parent=axisScale(element.parentElement);
    const zoom=style.zoom.endsWith('%')?parseFloat(style.zoom)/100:parseFloat(style.zoom||'1');
    // CSS individual scale precedes the transform list in the composed
    // matrix: S * M. After a quarter turn, b is on Y and c is on X.
    const a=local.a*sx*zoom,b=local.b*sy*zoom,c=local.c*sx*zoom,d=local.d*sy*zoom;
    const result={a:parent.a*a+parent.c*b,b:parent.b*a+parent.d*b,
                  c:parent.a*c+parent.c*d,d:parent.b*c+parent.d*d};
    scaleCache.set(element,result);return result;
  };
  const clipFor = (element,includeSelf=false) => {
    let left=0,top=0,right=width,bottom=height;
    for(let parent=element;parent;parent=parent.parentElement) {
      if(parent===document.documentElement||parent===document.scrollingElement)continue;
      const style=getComputedStyle(parent),r=parent.getBoundingClientRect(),scale=axisScale(parent);
      // Signed axis permutations (including exact quarter/half turns) still
      // map local rectangles to viewport rectangles. Use actual floating
      // border-box dimensions; offset/client dimensions are integer CSS px.
      const localWidth=scale.a?r.width/Math.abs(scale.a):r.height/Math.abs(scale.b);
      const localHeight=scale.d?r.height/Math.abs(scale.d):r.width/Math.abs(scale.c);
      const originX=r.left-Math.min(0,scale.a*localWidth)-Math.min(0,scale.c*localHeight);
      const originY=r.top-Math.min(0,scale.b*localWidth)-Math.min(0,scale.d*localHeight);
      const mapped=(x,y)=>({x:originX+scale.a*x+scale.c*y,y:originY+scale.b*x+scale.d*y});
      const mappedRect=(x1,y1,x2,y2)=>{
        const points=[mapped(x1,y1),mapped(x1,y2),mapped(x2,y1),mapped(x2,y2)];
        return {left:Math.min(...points.map(p=>p.x)),right:Math.max(...points.map(p=>p.x)),
                top:Math.min(...points.map(p=>p.y)),bottom:Math.max(...points.map(p=>p.y))};
      };
      const legacy=style.clip.match(/^rect\(([^)]+)\)$/);
      if(legacy) {
        const parts=legacy[1].split(/[,\s]+/).filter(Boolean).map(parseFloat);
        if(parts.length===4&&parts.every(Number.isFinite)) {
          const box=mappedRect(parts[3],parts[0],parts[1],parts[2]);
          top=Math.max(top,box.top);bottom=Math.min(bottom,box.bottom);
          left=Math.max(left,box.left);right=Math.min(right,box.right);
        }
      }
      if(style.clipPath==='inset(50%)'){left=Math.max(left,r.left+r.width/2);right=Math.min(right,r.left+r.width/2);top=Math.max(top,r.top+r.height/2);bottom=Math.min(bottom,r.top+r.height/2);}
      if(parent===element&&!includeSelf)continue;
      // CSS propagates BODY overflow to the viewport when the root overflow
      // is visible. Its scrolled border box is then not a clipping ancestor.
      if(parent===document.body) {
        const rootStyle=getComputedStyle(document.documentElement);
        if(rootStyle.overflowX==='visible'&&rootStyle.overflowY==='visible')continue;
      }
      // clientWidth/Height and offsetWidth/Height are integer CSS pixels;
      // the actual border box and text ranges retain subpixel precision.
      // Restore only that rounding remainder, without relaxing a real clip
      // or any of the text owner's occlusion hit tests below.
      const remainderX=localWidth-parent.offsetWidth,remainderY=localHeight-parent.offsetHeight;
      const roundingX=Math.abs(remainderX)<=0.5?remainderX:0;
      const roundingY=Math.abs(remainderY)<=0.5?remainderY:0;
      if(/^(hidden|auto|scroll|clip)$/.test(style.overflowX)) {
        const a=mapped(parent.clientLeft,0),b=mapped(parent.clientLeft+parent.clientWidth+roundingX,0);
        if(scale.a){left=Math.max(left,Math.min(a.x,b.x));right=Math.min(right,Math.max(a.x,b.x));}
        else {top=Math.max(top,Math.min(a.y,b.y));bottom=Math.min(bottom,Math.max(a.y,b.y));}
      }
      if(/^(hidden|auto|scroll|clip)$/.test(style.overflowY)) {
        const a=mapped(0,parent.clientTop),b=mapped(0,parent.clientTop+parent.clientHeight+roundingY);
        if(scale.d){top=Math.max(top,Math.min(a.y,b.y));bottom=Math.min(bottom,Math.max(a.y,b.y));}
        else {left=Math.max(left,Math.min(a.x,b.x));right=Math.min(right,Math.max(a.x,b.x));}
      }
    }
    return {left,top,right,bottom};
  };
  const transparentInlineCache=new WeakMap();
  const emptyInlineAt = (element,x,y) => {
    let data=transparentInlineCache.get(element);
    if(!data) {
      const style=getComputedStyle(element);
      const noPaint=s=>s.backgroundColor==='rgba(0, 0, 0, 0)'&&s.backgroundImage==='none'&&
        ['Top','Right','Bottom','Left'].every(side=>parseFloat(s[`border${side}Width`])===0)&&
        s.boxShadow==='none'&&s.textShadow==='none'&&s.filter==='none'&&s.backdropFilter==='none'&&s.transform==='none';
      // Normal inline padding can overlap another line without painting over
      // it (e.g. a padded section link). Do not generalize this exception to
      // positioned overlays, painted backgrounds, borders or pseudo content.
      const empty=style.display==='inline'&&style.position==='static'&&noPaint(style)&&
        ['::before','::after'].every(p=>['none','normal'].includes(getComputedStyle(element,p).content));
      const range=document.createRange();range.selectNodeContents(element);
      data={empty,rects:empty?[...range.getClientRects()]:[]};transparentInlineCache.set(element,data);
    }
    return data.empty&&!data.rects.some(r=>x>=r.left&&x<r.right&&y>=r.top&&y<r.bottom);
  };
  const textHit = (x,y,owner) => {
    const hit=document.elementFromPoint(x,y);
    if(!hit)return false;
    if(hit===owner||hit.contains(owner))return true;
    if(!emptyInlineAt(hit,x,y))return false;
    // Require the actual owner underneath every ignored transparent inline.
    // owner.contains(hit) alone would accept a sibling overlay inside a P.
    for(const layer of document.elementsFromPoint(x,y)) {
      if(layer===owner||layer.contains(owner))return true;
      if(!emptyInlineAt(layer,x,y))return false;
    }
    return false;
  };
  // Text visibility belongs to the text node's actual owner, not any of its
  // descendants: a sibling overlay inside the same paragraph is not its text.
  // This is conservative DOM hit evidence, not an image/semantic assessment.
  const exposedRect = (rect,owner,clip) => {
    if(rect.width<=0||rect.height<=0||rect.left<clip.left||rect.top<clip.top||rect.right>clip.right||rect.bottom>clip.bottom)return false;
    // Keep probes at least one CSS pixel inside a fragment. Chromium may round
    // half-pixel edge hits into the next normal inline span or form control.
    const insetX=Math.min(1,rect.width/4),insetY=Math.min(1,rect.height/4);
    const xs=[rect.left+insetX,(rect.left+rect.right)/2,rect.right-insetX];
    const ys=[rect.top+insetY,(rect.top+rect.bottom)/2,rect.bottom-insetY];
    return xs.every(x=>ys.every(y=>textHit(x,y,owner)));
  };
  const nativeValueVisible = node => {
    if(!node.matches('input,textarea,select')||node.type==='password')return false;
    if(!exposedRect(node.getBoundingClientRect(),node,clipFor(node)))return false;
    // A visible border box does not prove a native value hidden by internal
    // scrolling. Never promote a clipped textarea/input's full DOM value.
    if(node.scrollWidth>node.clientWidth||node.scrollHeight>node.clientHeight)return false;
    if(node.tagName==='SELECT') {
      const style=getComputedStyle(node),canvas=document.createElement('canvas').getContext('2d');
      if(!canvas||!style.font)return false;
      canvas.font=style.font;
      const text=[...node.selectedOptions].map(o=>o.label||o.textContent).join(' ');
      if(canvas.measureText(text).width>node.clientWidth-parseFloat(style.paddingLeft||0)-parseFloat(style.paddingRight||0)-16)return false;
    }
    return true;
  };
  const textCache=new WeakMap(),textEdges=new WeakMap();
  const segmenter=new Intl.Segmenter(undefined,{granularity:'grapheme'});
  const measureContext=document.createElement('canvas').getContext('2d');
  const inkRect = (rect,text,style) => {
    // Range rectangles describe the fallback font cell, including blank
    // ascent/descent. A 21px line may have a 22px cell with fully visible ink.
    // Use original-font vertical ink metrics only when they agree with the
    // actual range's font cell; unsupported layout keeps the stricter Range.
    if(!measureContext||!text.trim()||style.writingMode!=='horizontal-tb'||style.transform!=='none'||style.textTransform!=='none'||!style.font)return rect;
    measureContext.font=style.font;
    const m=measureContext.measureText(text),cell=m.fontBoundingBoxAscent+m.fontBoundingBoxDescent;
    if(!Number.isFinite(cell)||Math.abs(cell-rect.height)>0.01||m.actualBoundingBoxAscent+m.actualBoundingBoxDescent<=0)return rect;
    const baseline=rect.top+m.fontBoundingBoxAscent;
    const top=Math.max(rect.top,baseline-m.actualBoundingBoxAscent),bottom=Math.min(rect.bottom,baseline+m.actualBoundingBoxDescent);
    return {left:rect.left,right:rect.right,top,bottom,width:rect.width,height:bottom-top};
  };
  const visibleText = node => {
    if(textCache.has(node))return textCache.get(node);
    if(node.nodeType===Node.COMMENT_NODE)return '';
    if(node.nodeType===Node.ELEMENT_NODE) {
      const style=getComputedStyle(node);
      if(style.display==='none'||style.visibility!=='visible'||Number(style.opacity)===0)return '';
      const text=[...node.childNodes].map(visibleText).join(' ');
      textCache.set(node,text);return text;
    }
    if(node.nodeType!==Node.TEXT_NODE||!node.parentElement)return '';
    const owner=node.parentElement;
    if(owner.checkVisibility&&!owner.checkVisibility({checkOpacity:true,checkVisibilityCSS:true}))return '';
    const range=document.createRange();range.selectNodeContents(node);
    const rectangles=[...range.getClientRects()];
    const clip=clipFor(owner,true);
    const textStyle=getComputedStyle(owner);
    if(!rectangles.some(r=>r.right>clip.left&&r.bottom>clip.top&&r.left<clip.right&&r.top<clip.bottom))return '';
    let result='',gap=false,startsVisible=false,endsVisible=false,hasText=false;
    // Grapheme boundaries preserve original surrogate pairs/combining marks.
    // Every retained range is tested where it is actually painted; a bounding
    // box merely intersecting the viewport never proves its text is exposed.
    for(const part of segmenter.segment(node.textContent)) {
      range.setStart(node,part.index);range.setEnd(node,part.index+part.segment.length);
      const boxes=[...range.getClientRects()].filter(r=>r.width>0&&r.height>0);
      const visible=!!boxes.length&&boxes.every(r=>exposedRect(inkRect(r,part.segment,textStyle),owner,clip));
      if(part.segment.trim()) {
        if(!hasText)startsVisible=visible;
        endsVisible=visible;hasText=true;
      }
      if(visible) {
        if(gap&&result&&!/\s$/.test(result))result+=' ';
        result+=part.segment;gap=false;
      } else gap=true;
    }
    textEdges.set(node,{starts_visible:startsVisible,ends_visible:endsVisible});
    textCache.set(node,result);return result;
  };
  const name = element => {
    // Image names describe accessible DOM attributes, not pixels/visible prose.
    // Keep empty names empty; never infer a large news image's subject.
    if(element.tagName==='IMG')return clean(element.getAttribute('alt')||element.getAttribute('title'));
    const labelled = (element.getAttribute('aria-labelledby') || '').split(/\s+/)
      .map(id => {const node=document.getElementById(id);return node?visibleText(node):'';}).join(' ').trim();
    const label = element.labels ? [...element.labels].map(visibleText).join(' ') : '';
    let adjacentLabel='';
    if (element.matches('input,textarea,select')) {
      let container=element.parentElement;
      for(let depth=0;container&&container!==document.body&&depth<3;depth++,container=container.parentElement) {
        const labels=[...container.children].filter(node=>node.matches('label'));
        if(labels.length===1){adjacentLabel=visibleText(labels[0]);break;}
      }
    }
    const direct = [...element.childNodes].filter(n => n.nodeType === Node.TEXT_NODE)
      .map(visibleText).join(' ');
    const interactive = element.matches('a,button,label,summary,[role=button],[role=link],[role=option]');
    return clean(element.getAttribute('aria-label') || labelled || label || (element.matches('input') && (element.closest('.layui-form-select') || element.getAttribute('role')==='combobox') ? element.value : '') || adjacentLabel ||
      (interactive ? visibleText(element) : direct) || element.getAttribute('placeholder') ||
      element.getAttribute('title') || (element.matches('input[type=submit],input[type=button]') ? element.value : ''));
  };
  for (const element of document.querySelectorAll('body *')) {
    if (element.matches('script,style,noscript,template,svg,svg *')) continue;
    const style = getComputedStyle(element), rect = element.getBoundingClientRect();
    if (style.display === 'none' || style.visibility !== 'visible' || Number(style.opacity) === 0 ||
        rect.width <= 0 || rect.height <= 0 || rect.bottom <= 0 || rect.right <= 0 || rect.top >= height || rect.left >= width) continue;
    if (element.checkVisibility && !element.checkVisibility({checkOpacity:true,checkVisibilityCSS:true})) continue;
    axisScale(element);
    const opaqueFrame=element.matches('iframe,frame');
    const clip=clipFor(element);
    const bbox = [Math.max(0,Math.floor(Math.max(rect.left,clip.left))),Math.max(0,Math.floor(Math.max(rect.top,clip.top))),
                  Math.min(width,Math.ceil(Math.min(rect.right,clip.right))),Math.min(height,Math.ceil(Math.min(rect.bottom,clip.bottom)))];
    if (bbox[0] >= bbox[2] || bbox[1] >= bbox[3]) continue;
    const x = (bbox[0]+bbox[2]-1)/2, y = (bbox[1]+bbox[3]-1)/2;
    const hit = document.elementFromPoint(x,y);
    // The host document provides a real container rectangle, never the pixels
    // or text of an embedded document. Preserve an opaque, non-target window;
    // no child text, visual inference or frame action is synthesized.
    const text = opaqueFrame?'':name(element);
    const inputable = !element.readOnly && !element.matches('input[type=range],input[type=color],input[type=file],input[type=hidden],input[type=reset],input[type=image]') && element.matches('textarea,input:not([type=checkbox]):not([type=radio]):not([type=button]):not([type=submit]),[contenteditable=true]');
    const clickable = !opaqueFrame&&(element.matches('a[href],button,select,summary,input,label,[role=button],[role=link],[role=option],[role=tab],[role=checkbox],[role=radio]') ||
       element.hasAttribute('onclick') || style.cursor === 'pointer');
    const scrollable = /(auto|scroll)/.test(style.overflowY+style.overflowX) && (element.scrollHeight>element.clientHeight || element.scrollWidth>element.clientWidth);
    const image=element.tagName==='IMG';
    if (!text && !inputable && !clickable && !scrollable && !image && !opaqueFrame && element !== target) continue;
    if(image) {
      // A noninteractive image still carries real visible geometry. Retain a
      // viewport/ancestor-clipped box if any sampled point is exposed; a modal
      // covering the complete image must not create an image record.
      const xs=[bbox[0]+0.5,(bbox[0]+bbox[2])/2,bbox[2]-0.5],ys=[bbox[1]+0.5,(bbox[1]+bbox[3])/2,bbox[3]-0.5];
      if(!xs.some(px=>ys.some(py=>{const h=document.elementFromPoint(px,py);return !!h&&(h===element||h.contains(element));})))continue;
    } else if (hit && hit !== element && !element.contains(hit) && !hit.contains(element)) continue;
    const tag = element.tagName.toLowerCase();
    const role = element.getAttribute('role') || tag;
    const renderer=element.matches('.layui-form-radio,.layui-form-checkbox');
    const previous=element.previousElementSibling;
    const labelControl=element.matches('label')?element.control:null;
    const backing=labelControl?.matches('input[type=radio],input[type=checkbox]')?labelControl:
      renderer&&previous?.matches('input[type=radio],input[type=checkbox]')?previous:null;
    let type = ({a:'link',button:'button',input:'input',textarea:'input',select:'select',option:'option',label:'text',img:'image'})[tag] ||
               ({button:'button',link:'link',tab:'tab',checkbox:'checkbox',radio:'radio',textbox:'input',option:'option'})[role] || 'text';
    if(opaqueFrame)type='window';
    if (tag === 'input' && ['checkbox','radio'].includes(element.type)) type=element.type;
    if(tag==='input'&&element.type==='range')type='slider';
    if(backing)type=backing.type;
    const enabled = !element.matches(':disabled,.layui-disabled,.is-disabled') && !element.disabled && !backing?.disabled && element.getAttribute('aria-disabled') !== 'true';
    let state = !enabled ? 'disabled' : document.activeElement===element ? 'focused' : 'default';
    if(backing)state=backing.checked?'checked':'unchecked';
    else if (element.matches('input[type=checkbox],input[type=radio]')) state=element.checked?'checked':'unchecked';
    else if (element.getAttribute('aria-selected')==='true' || element.getAttribute('aria-pressed')==='true' || element.selected || element.classList.contains('active') || element.classList.contains('selected') || element.classList.contains('layui-this')) state='selected';
    else if (element.hasAttribute('aria-expanded')) state=element.getAttribute('aria-expanded')==='true'?'expanded':'collapsed';
    nodes.push(element);
    if(!observer.ids.has(element))observer.ids.set(element,`e_${observer.next++}`);
    records.push({element_id:observer.ids.get(element),parent_id:'root',element_type:type,native_role:role,
      text:backing?(backing.title||clean(visibleText(element))):text,bbox,clickable,inputable,scrollable,visible:true,enabled,state});
  }
  const byNode = new Map(nodes.map((node,i)=>[node,records[i].element_id]));
  for (let i=0;i<nodes.length;i++) {
    let parent=nodes[i].parentElement;
    while(parent && !byNode.has(parent)) parent=parent.parentElement;
    records[i].parent_id=parent?byNode.get(parent):'root';
  }
  const values = nodes.map((node,i)=>({element_id:records[i].element_id,
    value: typeof node.value==='string'?node.value:null,
    display_value:node.tagName==='SELECT'?[...node.selectedOptions].map(option=>option.textContent.trim()).join(' '):(typeof node.value==='string'?node.value:null), value_visible:nativeValueVisible(node),focused:document.activeElement===node,
    choice:node.tagName==='SELECT'||node.getAttribute('role')==='combobox'||!!node.closest('.layui-form-select'),selection_start:typeof node.selectionStart==='number'?node.selectionStart:null,
    selection_end:typeof node.selectionEnd==='number'?node.selectionEnd:null,input_type:node.type||'',readonly:!!node.readOnly,checked:typeof node.checked==='boolean'?node.checked:null})).filter(x=>x.value!==null||x.focused||x.checked!==null);
  const targetIndex=nodes.indexOf(target);
  let targetInfo=null;
  if (targetIndex>=0) {
    const e=records[targetIndex];
    // A wrapped inline link's bounding rectangle includes empty line gaps.
    // Use a real visible client-rectangle point if its overall center misses.
    const rectangles=[{left:e.bbox[0],top:e.bbox[1],right:e.bbox[2],bottom:e.bbox[3]},...target.getClientRects()];
    const candidates=rectangles.map(r=>({left:Math.max(r.left,e.bbox[0]),top:Math.max(r.top,e.bbox[1]),right:Math.min(r.right,e.bbox[2]),bottom:Math.min(r.bottom,e.bbox[3])}))
      .filter(r=>r.right>r.left&&r.bottom>r.top)
      .map(r=>[Math.floor((r.left+r.right-1)/2),Math.floor((r.top+r.bottom-1)/2)]);
    const canHit=([x,y])=>{const hit=document.elementFromPoint(x,y);return !!hit&&(hit===target||target.contains(hit));};
    const coordinate=candidates.find(canHit)||candidates[0];
    // Evidence for the narrower M4 text-target adapter. Accessible names stay
    // in tree.text, but aria-label/title alone never prove a readable label.
    const labelSources=[];
    const addLabel=(kind,text)=>{text=clean(text||'');if(text)labelSources.push({kind,text});};
    addLabel('rendered_target_text',visibleText(target));
    for(const label of target.labels||[])addLabel('rendered_associated_label',visibleText(label));
    for(const id of (target.getAttribute('aria-labelledby')||'').split(/\s+/).filter(Boolean)) {
      const label=document.getElementById(id);
      if(label)addLabel('rendered_labelledby_text',visibleText(label));
    }
    // Bootstrap-style input groups sometimes have a visible addon rather than
    // an HTML-associated label. Accept only an unambiguous two-branch group;
    // proximity elsewhere in a form never establishes a label relationship.
    const adjacentInputGroupLabel=()=>{
      if(!target.matches('input,textarea,select')||target.readOnly||target.disabled||
         target.matches('input[type=hidden],input[type=range],input[type=color],input[type=file],input[type=checkbox],input[type=radio],input[type=button],input[type=submit],input[type=reset],input[type=image]'))return '';
      const group=target.parentElement;
      if(!group?.matches('.input-group')||group.children.length!==2||group.querySelector('.input-group'))return '';
      const controls=group.querySelectorAll('input,textarea,select,button,[contenteditable],[role=textbox],[role=combobox],[role=spinbutton],[role=button]');
      const labels=group.querySelectorAll('.input-group-text');
      if(controls.length!==1||controls[0]!==target||labels.length!==1)return '';
      const label=labels[0],branch=label.parentElement===group?label:label.parentElement;
      if(!label.matches('span')||label.children.length||branch.parentElement!==group)return '';
      if(branch!==label&&(!branch.matches('.input-group-prepend,.input-group-append')||branch.children.length!==1))return '';
      const hasOwnText=node=>[...node.childNodes].some(child=>child.nodeType===Node.TEXT_NODE&&clean(child.textContent));
      if(hasOwnText(group)||(branch!==label&&hasOwnText(branch)))return '';
      // Full original text must survive the existing per-grapheme clipping and
      // occlusion checks. Partial visible fragments cannot name the control.
      const source=clean(label.textContent),text=clean(visibleText(label));
      if(!source||text!==source)return '';
      const style=getComputedStyle(label);
      if(parseFloat(style.fontSize)<10||style.textTransform!=='none'||
         /^(transparent|rgba\([^)]*,\s*0\))$/.test(style.color)||
         /^(transparent|rgba\([^)]*,\s*0\))$/.test(style.webkitTextFillColor)||
         !['::before','::after'].every(p=>['none','normal'].includes(getComputedStyle(label,p).content)))return '';
      for(let parent=label;parent;parent=parent.parentElement) {
        const painted=getComputedStyle(parent);
        if(Number(painted.opacity)!==1||painted.filter!=='none')return '';
      }
      const a=label.getBoundingClientRect(),b=target.getBoundingClientRect();
      // Addons sit beside their single control on the same visual row. Allow
      // Bootstrap's shared 1px border, but no wider overlap or distant text.
      const gap=Math.max(a.left,b.left)-Math.min(a.right,b.right);
      const overlap=Math.min(a.bottom,b.bottom)-Math.max(a.top,b.top);
      if(gap < -1||gap>16||overlap<0.8*Math.min(a.height,b.height)||
         Math.abs((a.top+a.bottom-b.top-b.bottom)/2)>8)return '';
      // The later-painted neighbor can own that shared border's hit point.
      // Exclude only their measured <=1px intersection from box probes; all
      // original label graphemes above must still be fully exposed.
      const unsharedBox=(rect,other)=>{
        let left=rect.left,right=rect.right;
        if(gap<0) {if(left<other.left)right=other.left;else left=other.right;}
        return {left,right,top:rect.top,bottom:rect.bottom,width:right-left,height:rect.height};
      };
      const labelBox=unsharedBox(a,b),targetBox=unsharedBox(b,a);
      if(!exposedRect(labelBox,label,clipFor(label))||!exposedRect(targetBox,target,clipFor(target)))return '';
      // The generic 3x3 hit probes can miss an overlay between the center and
      // edge of a wide input. This new inference additionally checks its area
      // on a 4 CSS-pixel grid; no existing visibility rule is relaxed.
      for(let x=targetBox.left+1;x<targetBox.right;x+=4)for(let y=targetBox.top+1;y<targetBox.bottom;y+=4) {
        if(!textHit(x,y,target))return '';
      }
      return text;
    };
    addLabel('rendered_adjacent_input_group_label',adjacentInputGroupLabel());
    if(nativeValueVisible(target)) {
      if(target.tagName==='SELECT')addLabel('visible_selected_option',[...target.selectedOptions].map(o=>o.label||o.textContent).join(' '));
      else if(target.matches('input,textarea'))addLabel(target.value?'visible_native_value':'visible_placeholder',target.value||target.placeholder);
    }
    targetInfo={element_id:e.element_id,coordinate,hit_valid:canHit(coordinate),bbox:e.bbox,text:e.text,enabled:e.enabled,
      focused:document.activeElement===target,value:typeof target.value==='string'?target.value:null,
      visible_label_evidence:labelSources};
  }
  const visiblePieces=[];
  const walker=document.createTreeWalker(document.body,NodeFilter.SHOW_TEXT);
  for(let node=walker.nextNode();node;node=walker.nextNode()) {
    const parent=node.parentElement;
    if(!parent||parent.closest('script,style,noscript,template')||!parent.checkVisibility({checkOpacity:true,checkVisibilityCSS:true}))continue;
    const text=clean(visibleText(node));if(text)visiblePieces.push(text);
  }
  for(const node of nodes) {
    if(!node.matches('input,textarea')||node.type==='password'||node.type==='range'||node.type==='file')continue;
    // Native input values have no DOM Text Range. Retain the value only if the
    // whole control box is exposed; partial occlusion cannot prove its string.
    const value=node.value||node.placeholder;
    if(value&&nativeValueVisible(node))visiblePieces.push(value);
  }
  const inlineText = node => {
    if(node.nodeType===Node.TEXT_NODE)return visibleText(node);
    if(node.nodeType!==Node.ELEMENT_NODE||!node.checkVisibility({checkOpacity:true,checkVisibilityCSS:true}))return '';
    if(node.tagName==='BR')return '\n';
    return [...node.childNodes].map(inlineText).join('');
  };
  const edgeText = (node,last=false) => {
    if(node.nodeType===Node.TEXT_NODE)return node.textContent.trim()?node:null;
    const children=[...node.childNodes];if(last)children.reverse();
    for(const child of children){const edge=edgeText(child,last);if(edge)return edge;}
    return null;
  };
  // Raw-only block evidence preserves inline reading order and reports actual
  // boundary visibility. Original DOM text supplies boundaries, never content
  // for a hidden range. The customer's UI-element schema remains unchanged.
  const textBlocks=[];
  for(const paragraph of document.querySelectorAll('p')) {
    const text=clean(inlineText(paragraph));if(!text)continue;
    if(!observer.ids.has(paragraph))observer.ids.set(paragraph,`e_${observer.next++}`);
    const first=edgeText(paragraph),last=edgeText(paragraph,true);
    // Source punctuation supplies sentence boundaries, never hidden content.
    // Only sentences whose entire characters are in the clipped visible
    // reading order may be used as complete narrative quotations.
    const normalized=s=>s.replace(/\s+/g,'');
    const source=clean(paragraph.textContent),sourceParts=[];
    let sentenceStart=0;
    for(let end=0;end<source.length;end++) {
      if(!/[。！？]/.test(source[end]))continue;
      // Keep source characters intact, including unusual numeric punctuation.
      // A coordinate such as 118。30 must never yield a quotation ending 118。.
      if(source[end]==='。'&&/\d$/.test(source.slice(0,end).trimEnd())&&/^\d/.test(source.slice(end+1).trimStart()))continue;
      while(end+1<source.length&&/[”’」』）》】)]/.test(source[end+1]))end++;
      sourceParts.push(source.slice(sentenceStart,end+1));sentenceStart=end+1;
    }
    const complete=[];
    for(let i=0;i<sourceParts.length;i++) {
      let sentence=sourceParts[i];
      const balanced=s=>[['“','”'],['‘','’'],['「','」'],['『','』']].every(([a,b])=>s.split(a).length===s.split(b).length);
      for(let j=i+1;!balanced(sentence)&&j<sourceParts.length;j++)sentence+=sourceParts[j];
      if(balanced(sentence)&&normalized(text).includes(normalized(sentence)))complete.push(clean(sentence));
    }
    textBlocks.push({element_id:observer.ids.get(paragraph),visible_text:text,complete_sentences:complete,
      starts_visible:!!textEdges.get(first)?.starts_visible,ends_visible:!!textEdges.get(last)?.ends_visible});
  }
  const assertionTargets=assertions.map(condition=>{
    if('visible_text' in condition)return null;
    const node=document.querySelectorAll(condition.selector)[condition.index||0];
    if(!node)return null;
    if(node.matches('iframe,frame'))throw new Error('UNSUPPORTED_FRAME: task completion cannot rely on an unread embedded document');
    const rect=node.getBoundingClientRect(),style=getComputedStyle(node),hit=document.elementFromPoint((rect.left+rect.right)/2,(rect.top+rect.bottom)/2);
    const control=node.tagName==='LABEL'?node.control:node;
    return {selector:condition.selector,index:condition.index||0,
      visible:(!node.checkVisibility||node.checkVisibility({checkOpacity:true,checkVisibilityCSS:true}))&&
        style.visibility==='visible'&&rect.width>0&&rect.height>0&&rect.left>=0&&rect.top>=0&&rect.right<=width&&rect.bottom<=height&&
        !!hit&&(hit===node||node.contains(hit)),
      text:clean(visibleText(node)),target_text:name(node),value:node.matches('input,textarea,select')&&typeof node.value==='string'?node.value:null,value_visible:nativeValueVisible(node),
      display_value:node.tagName==='SELECT'?[...node.selectedOptions].map(option=>clean(option.label||option.textContent)).join(' '):
        (typeof node.value==='string'?node.value:null),
      checked:control?.matches('input[type=radio],input[type=checkbox]')?control.checked:null,
      disabled:node.matches(':disabled')||node.getAttribute('aria-disabled')==='true',
      bbox:[rect.left,rect.top,rect.right,rect.bottom]};
  });
  return {url:location.href,title:document.title,screen_resolution:[width,height],device_pixel_ratio:devicePixelRatio,
    scroll:[scrollX,scrollY],elements:records,values,target:targetInfo,
    visible_text:visiblePieces.join('\n'),text_blocks:textBlocks,
    embedded_frames:nodes.map((node,i)=>node.matches('iframe,frame')?{
      element_id:records[i].element_id,bbox:records[i].bbox,title:node.getAttribute('title')||'',
      src:node.getAttribute('src')||'',subtree:'opaque_unread',task_actions_supported:false,
      focused:document.activeElement===node}:null).filter(Boolean),
    ...(assertions.length?{assertion_targets:assertionTargets}:{} )};
}
