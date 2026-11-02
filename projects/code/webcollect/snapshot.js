/* Read-only visible DOM evidence. No page content, attributes or styles are changed. */
({selector = null, index = 0, assertions = [], protected_selectors = []} = {}) => {
  if(!document.body)throw new Error('DOCUMENT_NOT_READY: body absent during navigation');
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
  const nativeValueVisible = (node,allowEmptyPlaceholderTargetEvidence=false) => {
    if(!node.matches('input,textarea,select'))return false;
    const password=node.matches('input[type=password]');
    // Only the target-label call may expose an empty password placeholder.
    // Native password values and assertion values always keep the default false.
    if(password&&(!allowEmptyPlaceholderTargetEvidence||node.value!==''||node.disabled||node.readOnly||!node.placeholder))return false;
    const emptyPlaceholder=node.matches('input,textarea')&&node.value===''&&!!node.placeholder;
    // DOM values are not visible strings when their actual text fill merges
    // into the provable background. The same paint rule applies to prose and
    // labels; complex/unprovable backgrounds supply no native value evidence.
    if(!frameworkLabelPaint(node,emptyPlaceholder?getComputedStyle(node,'::placeholder'):null))return false;
    // Preserve the existing complete-control occlusion gate for value evidence.
    // A target placeholder is instead bound to its fully measured glyph area;
    // a sibling's shared border does not paint over that text.
    if((!emptyPlaceholder||!allowEmptyPlaceholderTargetEvidence)&&
       !exposedRect(node.getBoundingClientRect(),node,clipFor(node)))return false;
    // A visible border box does not prove a native value hidden by internal
    // scrolling. Never promote a clipped textarea/input's full DOM value.
    if(node.scrollWidth>node.clientWidth||node.scrollHeight>node.clientHeight)return false;
    if(emptyPlaceholder) {
      if(node.disabled||node.readOnly||!node.checkVisibility({checkOpacity:true,checkVisibilityCSS:true}))return false;
      const control=node.getBoundingClientRect(),clip=clipFor(node);
      if(control.width<=0||control.height<=0||control.left<clip.left||control.top<clip.top||
         control.right>clip.right||control.bottom>clip.bottom)return false;
      const text=node.placeholder,style=getComputedStyle(node),placeholder=getComputedStyle(node,'::placeholder');
      // Native placeholder glyphs have no DOM Text Range. Measure their actual
      // computed font, reject invisible/unsupported paint, then hit-test the
      // complete measured text rectangle. A visible input box alone is not proof.
      if(text!==text.trim()||text.length>256||/[\r\n\t]/.test(text)||
         !placeholder.font||parseFloat(placeholder.fontSize)<10||parseFloat(style.fontSize)<10||
         placeholder.writingMode!=='horizontal-tb'||placeholder.textTransform!=='none'||
         style.direction!=='ltr'||!['start','left'].includes(style.textAlign)||parseFloat(style.textIndent)!==0||
         !['normal','0px'].includes(placeholder.letterSpacing)||!['normal','0px'].includes(placeholder.wordSpacing)||
         placeholder.opacity!=='1'||placeholder.textShadow!=='none'||placeholder.filter!=='none'||
         placeholder.mixBlendMode!=='normal')return false;
      const rgba=frameworkColor;
      const foreground=rgba(placeholder.color),fill=rgba(placeholder.webkitTextFillColor);
      if(!foreground||!fill||foreground[3]!==1||fill[3]!==1)return false;
      let background=null;
      for(let owner=node;owner;owner=owner.parentElement) {
        const paint=getComputedStyle(owner);
        if(paint.opacity!=='1'||paint.filter!=='none'||paint.mixBlendMode!=='normal'||
           paint.maskImage!=='none'||paint.contentVisibility!=='visible')return false;
        for(const pseudo of ['::before','::after']) {
          if(!['none','normal'].includes(getComputedStyle(owner,pseudo).content))return false;
        }
        if(!background) {
          const color=rgba(paint.backgroundColor);
          if(!color||color[3]!==0&&color[3]!==1)return false;
          if(color[3]===1) {if(paint.backgroundImage!=='none')return false;background=color;}
        }
      }
      if(!background)return false;
      const contrast=color=>frameworkContrast(color,background);
      if(contrast(foreground)<3||contrast(fill)<3)return false;
      const scale=axisScale(node);
      if(scale.b!==0||scale.c!==0||scale.a<=0||scale.d<=0)return false;
      const box=node.getBoundingClientRect(),context=document.createElement('canvas').getContext('2d');
      if(!context||!document.fonts.check(placeholder.font,text))return false;
      context.font=placeholder.font;
      const metrics=context.measureText(text),sx=scale.a,sy=scale.d;
      const left=box.left+(parseFloat(style.borderLeftWidth)+parseFloat(style.paddingLeft))*sx;
      const top=box.top+(parseFloat(style.borderTopWidth)+parseFloat(style.paddingTop))*sy;
      const contentWidth=box.width/sx-parseFloat(style.borderLeftWidth)-parseFloat(style.borderRightWidth)-parseFloat(style.paddingLeft)-parseFloat(style.paddingRight);
      const contentHeight=box.height/sy-parseFloat(style.borderTopWidth)-parseFloat(style.borderBottomWidth)-parseFloat(style.paddingTop)-parseFloat(style.paddingBottom);
      const cell=metrics.fontBoundingBoxAscent+metrics.fontBoundingBoxDescent;
      const line=placeholder.lineHeight==='normal'?cell:parseFloat(placeholder.lineHeight);
      if(![contentWidth,contentHeight,cell,line,metrics.width,metrics.actualBoundingBoxAscent,metrics.actualBoundingBoxDescent].every(Number.isFinite)||
         contentWidth<=0||contentHeight<=0||metrics.width>contentWidth||line>contentHeight+.01||
         metrics.actualBoundingBoxAscent+metrics.actualBoundingBoxDescent<=0)return false;
      const baseline=top+((contentHeight-cell)/2+metrics.fontBoundingBoxAscent)*sy;
      const ink={left:left-metrics.actualBoundingBoxLeft*sx,right:left+metrics.actualBoundingBoxRight*sx,
        top:baseline-metrics.actualBoundingBoxAscent*sy,bottom:baseline+metrics.actualBoundingBoxDescent*sy};
      ink.width=ink.right-ink.left;ink.height=ink.bottom-ink.top;
      if(ink.left<left||ink.right>left+contentWidth*sx||ink.top<top||ink.bottom>top+contentHeight*sy||
         !exposedRect(ink,node,clipFor(node,true)))return false;
      for(let x=ink.left+.5;x<ink.right;x+=1)for(let y=ink.top+.5;y<ink.bottom;y+=1) {
        if(!textHit(x,y,node))return false;
      }
    }
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
    if(!frameworkLabelPaint(owner,textStyle))return '';
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
  const frameworkColorCache=new Map();let frameworkColorContext=null;
  const frameworkColor = value => {
    if(typeof value!=='string')return null;
    const match=value.match(/^rgba?\(([^)]+)\)$/);
    if(match) {
      const values=match[1].split(/[,\s/]+/).filter(Boolean).map(Number);
      if(values.length===3)values.push(1);
      return values.length===4&&values.every(Number.isFinite)&&values.slice(0,3).every(v=>v>=0&&v<=255)&&
        values[3]>=0&&values[3]<=1?values:null;
    }
    if(frameworkColorCache.has(value))return frameworkColorCache.get(value);
    let result=null;
    try {
      // Concrete computed Color4 colors only. No gradients, relative colors,
      // unresolved components or arbitrary CSS parsing fallback is permitted.
      if(!/^(?:lab|lch|oklab|oklch|color)\([^()]*\)$/i.test(value)||
         /\b(?:from|none|var|env|calc|currentcolor)\b/i.test(value)||!CSS.supports('color',value))return null;
      const parts=value.slice(value.indexOf('(')+1,-1).split('/');
      if(parts.length>2)return null;
      let alpha=1;
      if(parts.length===2) {
        const token=parts[1].trim(),m=token.match(/^([+-]?(?:\d+(?:\.\d*)?|\.\d+)(?:e[+-]?\d+)?)(%)?$/i);
        if(!m)return null;
        alpha=Math.max(0,Math.min(1,Number(m[1])/(m[2]?100:1)));
        if(!Number.isFinite(alpha))return null;
      }
      if(!frameworkColorContext) {
        const canvas=document.createElement('canvas');canvas.width=canvas.height=1;
        frameworkColorContext=canvas.getContext('2d',{colorSpace:'srgb',willReadFrequently:true});
      }
      const context=frameworkColorContext;
      if(!context||context.getContextAttributes?.().colorSpace!=='srgb')return null;
      // Invalid fillStyle assignments are silently ignored by canvas. Two
      // different sentinels must therefore converge to the same native color.
      context.fillStyle='#010203';context.fillStyle=value;const first=context.fillStyle;
      context.fillStyle='#040506';context.fillStyle=value;
      if(context.fillStyle!==first)return null;
      context.globalCompositeOperation='copy';context.fillRect(0,0,1,1);
      const pixel=context.getImageData(0,0,1,1,{colorSpace:'srgb'}).data;
      if(pixel.length!==4||Math.abs(pixel[3]/255-alpha)>1/255+1e-12)return null;
      result=[pixel[0],pixel[1],pixel[2],alpha];
      // Readback is unpremultiplied 8-bit sRGB. Bound premultiplication,
      // alpha/readback rounding and unpremultiplication conservatively. Keep
      // the native CSS alpha exactly: a tiny painted pseudo must not become
      // falsely transparent just because its 8-bit sample rounded to zero.
      const error=alpha>0?Math.min(255,2/alpha+1):255;
      result.bounds=result.slice(0,3).map(v=>[Math.max(0,v-error),Math.min(255,v+error)]).concat([[alpha,alpha]]);
    } catch {}
    frameworkColorCache.set(value,result);return result;
  };
  const frameworkBounds=color=>color.bounds||color.map(value=>[value,value]);
  const compositeColor=(front,back)=>{
    const result=front.slice(0,3).map((v,i)=>v*front[3]+back[i]*(1-front[3])).concat(1);
    if(front.bounds||back.bounds) {
      const f=frameworkBounds(front),b=frameworkBounds(back);
      result.bounds=f.slice(0,3).map((range,i)=>{
        const corners=range.flatMap(v=>b[i].flatMap(w=>f[3].map(a=>v*a+w*(1-a))));
        return [Math.min(...corners),Math.max(...corners)];
      }).concat([[1,1]]);
    }
    return result;
  };
  const frameworkContrast=(front,back)=>{
    const luminance=color=>color.map(v=>v/255).map(v=>v<=.04045?v/12.92:((v+.055)/1.055)**2.4)
      .reduce((sum,value,index)=>sum+value*[.2126,.7152,.0722][index],0);
    const range=color=>{const bounds=frameworkBounds(color).slice(0,3);
      return [luminance(bounds.map(v=>v[0])),luminance(bounds.map(v=>v[1]))];};
    const a=range(front),b=range(back);
    // Overlapping luminance intervals cannot prove any contrast. Otherwise
    // compare the closest endpoints, never the favorable quantized samples.
    return a[1]<b[0]?(b[0]+.05)/(a[1]+.05):b[1]<a[0]?(a[0]+.05)/(b[1]+.05):1;
  };
  const frameworkLabelPaint = (label,foregroundStyle=null,minContrast=3) => {
    const style=foregroundStyle||getComputedStyle(label),fill=frameworkColor(style.webkitTextFillColor);
    if(!fill||fill[3]===0||style.textShadow!=='none'||style.backgroundClip==='text')return false;
    const layers=[];let background=null;
    for(let owner=label;owner;owner=owner.parentElement) {
      const paint=getComputedStyle(owner);
      if(Number(paint.opacity)!==1||paint.filter!=='none'||paint.backdropFilter!=='none'||
         paint.mixBlendMode!=='normal'||paint.maskImage!=='none'||paint.webkitMaskImage!=='none'||
         paint.contentVisibility!=='visible')return false;
      // Hit testing reports an ancestor for its generated paint (and omits
      // pointerless pseudo-elements). An opaque ancestor ::after can cover
      // every glyph without adding a foreign DOM rectangle. Its geometry is
      // unproven here. Empty transparent framework clearfixes paint nothing.
      for(const which of ['::before','::after']) {
        const pseudo=getComputedStyle(owner,which);
        if(['none','normal'].includes(pseudo.content)||pseudo.display==='none'||
           pseudo.visibility!=='visible'||Number(pseudo.opacity)===0)continue;
        const own=clean(pseudo.content.replace(/^(['"])([\s\S]*)\1$/,'$2'));
        const color=frameworkColor(pseudo.backgroundColor);
        if(own||!color||color[3]>0||pseudo.backgroundImage!=='none'||pseudo.boxShadow!=='none'||
           pseudo.filter!=='none'||pseudo.backdropFilter!=='none'||
           ['Top','Right','Bottom','Left'].some(side=>parseFloat(pseudo['border'+side+'Width'])>0&&
             (frameworkColor(pseudo['border'+side+'Color'])?.[3]??1)>0))return false;
      }
      if(!background) {
        const color=frameworkColor(paint.backgroundColor);
        if(!color||paint.backgroundImage!=='none')return false;
        layers.push(color);if(color[3]===1)background=color;
      }
    }
    // The unpainted CSS canvas is white only in the known light rendering
    // mode. A dark/unknown canvas or a complex painted background is unsupported.
    if(!background) {
      const scheme=getComputedStyle(document.documentElement).colorScheme;
      if(matchMedia('(prefers-color-scheme: dark)').matches||!['normal','light','light dark'].includes(scheme))return false;
      background=[255,255,255,1];
    }
    for(let i=layers.length-1;i>=0;i--)background=compositeColor(layers[i],background);
    const foreground=compositeColor(fill,background);
    return frameworkContrast(foreground,background)>=minContrast;
  };
  let frameworkSurfaces=null;
  const frameworkAreaExposed = (rect,owner,compatibleOwners=[]) => {
    const owners=[owner,...compatibleOwners];
    if(!frameworkSurfaces)frameworkSurfaces=[...document.querySelectorAll('body *')].filter(node=>
      !node.matches('script,style,noscript,template')).map(node=>({node,style:getComputedStyle(node),rects:[...node.getClientRects()]}));
    for(const {node,style,rects} of frameworkSurfaces) {
      if(owners.some(known=>node===known||node.contains(known)||known.contains(node))||style.display==='none'||style.visibility!=='visible')continue;
      for(const other of rects) {
        const left=Math.max(rect.left,other.left),right=Math.min(rect.right,other.right),
          top=Math.max(rect.top,other.top),bottom=Math.min(rect.bottom,other.bottom);
        if(right<=left||bottom<=top)continue;
        // As in exposedRect, keep full-sized fragments a CSS pixel inside
        // their edge: Chromium rounds half-pixel edge hits to the neighbor.
        // Thin intersections still get interior probes of their own extent.
        const dx=Math.min(1,(right-left)/4),dy=Math.min(1,(bottom-top)/4);
        for(const x of [left+dx,(left+right)/2,right-dx])for(const y of [top+dy,(top+bottom)/2,bottom-dy]) {
          if(!owners.some(known=>textHit(x,y,known)))return false;
        }
        // elementsFromPoint ignores pointer-events:none even when it paints
        // over the field. A possibly painted foreign surface cannot prove
        // exposure; empty transparent backdrops remain harmless.
        if(style.pointerEvents==='none'&&Number(style.opacity)!==0) {
          const color=frameworkColor(style.backgroundColor);
          const painted=!color||color[3]>0||style.backgroundImage!=='none'||style.boxShadow!=='none'||
            style.filter!=='none'||style.backdropFilter!=='none'||node.matches('img,svg,canvas,video,iframe,object')||
            ['Top','Right','Bottom','Left'].some(side=>parseFloat(style['border'+side+'Width'])>0&&
              (frameworkColor(style['border'+side+'Color'])?.[3]??1)>0)||
            [...node.childNodes].some(child=>child.nodeType===Node.TEXT_NODE&&clean(child.textContent))||
            ['::before','::after'].some(p=>!['none','normal'].includes(getComputedStyle(node,p).content));
          if(painted)return false;
        }
      }
    }
    return true;
  };
  const frameworkUploadLabel = label => {
    if(!label?.matches('label.layui-form-label')||label.children.length!==2)return null;
    const button=[...label.children].find(e=>e.matches('button.layui-btn[type=button]'));
    const file=[...label.children].find(e=>e.matches('input.layui-upload-file[type=file]'));
    if(!button||!file||getComputedStyle(file).display!=='none'||
       [...button.children].some(e=>!e.matches('i.layui-icon')||e.children.length))return null;
    const own=[...label.childNodes].filter(n=>n.nodeType===Node.TEXT_NODE);
    const source=clean(own.map(n=>n.textContent).join(' '));
    const text=clean(own.map(visibleText).join(' '));
    if(!source||source!==text)return null;
    return {button,file,source,text};
  };
  const frameworkLabelCache=new WeakMap();
  const frameworkLabelText = label => {
    if(!label.matches('label.layui-form-label'))return visibleText(label);
    if(frameworkLabelCache.has(label))return frameworkLabelCache.get(label);
    const upload=frameworkUploadLabel(label),own=[...label.childNodes].filter(n=>n.nodeType===Node.TEXT_NODE&&clean(n.textContent));
    const exposed=own.every(node=>{
      const range=document.createRange();range.selectNodeContents(node);
      return [...range.getClientRects()].every(rect=>frameworkAreaExposed(inkRect(rect,node.textContent,getComputedStyle(label)),label));
    });
    const value=(!label.children.length||upload)&&frameworkLabelPaint(label)&&exposed?
      upload?.text||visibleText(label):'';
    frameworkLabelCache.set(label,value);return value;
  };
  const name = element => {
    // Image names describe accessible DOM attributes, not pixels/visible prose.
    // Keep empty names empty; never infer a large news image's subject.
    if(element.tagName==='IMG')return clean(element.getAttribute('alt')||element.getAttribute('title'));
    const labelled = (element.getAttribute('aria-labelledby') || '').split(/\s+/)
      .map(id => {const node=document.getElementById(id);return node?visibleText(node):'';}).join(' ').trim();
    const label = element.labels ? [...element.labels].map(frameworkLabelText).join(' ') : '';
    let adjacentLabel='';
    if (element.matches('input,textarea,select')) {
      let container=element.parentElement;
      for(let depth=0;container&&container!==document.body&&depth<3;depth++,container=container.parentElement) {
        const labels=[...container.children].filter(node=>node.matches('label'));
        if(labels.length===1){adjacentLabel=frameworkLabelText(labels[0]);break;}
      }
    }
    const direct = [...element.childNodes].filter(n => n.nodeType === Node.TEXT_NODE)
      .map(visibleText).join(' ');
    const interactive = element.matches('a,button,label,summary,[role=button],[role=link],[role=option]');
    // An unlabelled native SELECT still paints its current selected option.
    // Use only the existing complete-value paint/occlusion/width proof; do not
    // expose hidden options or invent a name from a planned selection.
    const selected = element.tagName==='SELECT'&&nativeValueVisible(element,true)
      ? [...element.selectedOptions].map(option=>option.label||option.textContent).join(' ') : '';
    return clean(element.getAttribute('aria-label') || labelled || label || (element.matches('input') && (element.closest('.layui-form-select') || element.getAttribute('role')==='combobox') ? element.value : '') || adjacentLabel ||
      (interactive ? visibleText(element) : direct) || element.getAttribute('placeholder') ||
      element.getAttribute('title') || selected || (element.matches('input[type=submit],input[type=button]') ? element.value : ''));
  };
  const unrelatedTransforms=new WeakMap(),transformProofs=[];
  const boundedDecoration = element => {
    const st=getComputedStyle(element),r=element.getBoundingClientRect();
    if(element===target||!element.matches('img[alt=""][aria-hidden="true"]')||
       !['presentation','none'].includes(element.getAttribute('role'))||st.pointerEvents!=='none'||
       !element.complete||element.naturalWidth<=0||element.naturalHeight<=0||
       ['title','aria-label','aria-labelledby','tabindex'].some(k=>element.hasAttribute(k))||
       st.filter!=='none'||st.boxShadow!=='none'||st.clipPath!=='none'||st.maskImage!=='none'||
       r.left<0||r.top<0||r.right>width||r.bottom>height)return null;
    for(let p=element.parentElement;p;p=p.parentElement) {
      const a=getComputedStyle(p);
      if(p.matches('a,button,label,figure,[tabindex],[contenteditable=true],[role=img]')||
         [...p.attributes].some(x=>/^on/i.test(x.name))||a.transform!=='none'||
         (a.rotate&&a.rotate!=='none')||a.perspective!=='none'||
         !['visible','clip'].includes(a.overflowX)||!['visible','clip'].includes(a.overflowY))return null;
    }
    const overlap=b=>Math.min(r.right,b.right)>Math.max(r.left,b.left)&&Math.min(r.bottom,b.bottom)>Math.max(r.top,b.top);
    const protectedRegions=[];
    const walker=document.createTreeWalker(document.body,NodeFilter.SHOW_TEXT);
    while(walker.nextNode()) {
      const text=walker.currentNode;
      if(!clean(text.textContent)||text.parentElement.closest('script,style,noscript,template'))continue;
      const range=document.createRange();range.selectNodeContents(text);
      for(const box of range.getClientRects()) {if(overlap(box))return null;protectedRegions.push([box.left,box.top,box.right,box.bottom]);}
    }
    const selectors=['a[href],button,input,select,textarea,summary,[tabindex],[contenteditable=true],[role=button],[role=link]',
      ...protected_selectors,...assertions.filter(x=>x.selector).map(x=>x.selector)];
    for(const selector of selectors)for(const control of document.querySelectorAll(selector)) {
      const box=control.getBoundingClientRect();if(overlap(box))return null;
      protectedRegions.push([box.left,box.top,box.right,box.bottom]);
    }
    return {schema_version:'webcollect-unrelated-transform-1',bbox:[r.left,r.top,r.right,r.bottom],
      transform:st.transform,rotate:st.rotate,protected_regions:protectedRegions,
      relation:'explicit decorative image disjoint from every text/control/protected region',
      pixel_exclusion_allowed:false,actions_supported:false};
  };
  for (const element of document.querySelectorAll('body *')) {
    if (element.matches('script,style,noscript,template,svg,svg *')) continue;
    const style = getComputedStyle(element), rect = element.getBoundingClientRect();
    if (style.display === 'none' || style.visibility !== 'visible' || Number(style.opacity) === 0 ||
        rect.width <= 0 || rect.height <= 0 || rect.bottom <= 0 || rect.right <= 0 || rect.top >= height || rect.left >= width) continue;
    if (element.checkVisibility && !element.checkVisibility({checkOpacity:true,checkVisibilityCSS:true})) continue;
    // Empty, noninteractive decoration never enters the visible tree. Do not
    // demand target geometry from it before applying that existing filter.
    // Real text, controls, images, frames and explicit targets remain strict.
    const candidateScroll=/(auto|scroll)/.test(style.overflowY+style.overflowX)&&
      (element.scrollHeight>element.clientHeight||element.scrollWidth>element.clientWidth);
    if(element!==target&&!clean(element.textContent)&&
       !['aria-label','aria-labelledby','title','placeholder'].some(k=>element.hasAttribute(k))&&
       !element.matches('a[href],button,select,summary,input,textarea,label,img,iframe,frame,[contenteditable=true],[role=button],[role=link],[role=option],[role=tab],[role=checkbox],[role=radio]')&&
       !element.hasAttribute('onclick')&&style.cursor!=='pointer'&&!candidateScroll)continue;
    try {axisScale(element);} catch(error) {
      const proof=boundedDecoration(element);if(!proof)throw error;
      if(!observer.ids.has(element))observer.ids.set(element,`e_${observer.next++}`);
      proof.element_id=observer.ids.get(element);unrelatedTransforms.set(element,proof);transformProofs.push(proof);
      nodes.push(element);records.push({element_id:proof.element_id,parent_id:'root',element_type:'image',native_role:'img',
        text:'',bbox:[Math.floor(rect.left),Math.floor(rect.top),Math.ceil(rect.right),Math.ceil(rect.bottom)],
        clickable:false,inputable:false,scrollable:false,visible:true,enabled:false,state:'default',geometry_proof:proof});
      continue;
    }
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
    const landmark=element.matches('main,article,form,section,aside,nav,footer,[role=main],[role=region],[role=dialog],[role=alertdialog],[role=complementary]');
    if (!text && !inputable && !clickable && !scrollable && !image && !opaqueFrame && !landmark && element !== target) continue;
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
  // Chromium retargets the native number editor's selection to a collapsed
  // boundary immediately before the focused input. A document selection of
  // the same digits elsewhere must not be attributed to this field.
  const numberTextSelected = input => {
    if(document.activeElement!==input||!input.value)return false;
    const selection=window.getSelection();
    return !!selection&&selection.rangeCount===1&&selection.isCollapsed&&
      selection.anchorNode===input.parentNode&&selection.focusNode===input.parentNode&&
      input.parentNode.childNodes[selection.anchorOffset]===input&&selection.focusOffset===selection.anchorOffset&&
      selection.toString()===input.value;
  };
  const values = nodes.map((node,i)=>({element_id:records[i].element_id,
    ...(node.matches('input[type="number"]')?{all_text_selected:numberTextSelected(node)}:{}),
    value: typeof node.value==='string'?node.value:null,
    display_value:node.tagName==='SELECT'?[...node.selectedOptions].map(option=>option.textContent.trim()).join(' '):(typeof node.value==='string'?node.value:null), value_visible:nativeValueVisible(node),focused:document.activeElement===node,
    choice:node.tagName==='SELECT'||node.getAttribute('role')==='combobox'||!!node.closest('.layui-form-select'),selection_start:typeof node.selectionStart==='number'?node.selectionStart:null,
    selection_end:typeof node.selectionEnd==='number'?node.selectionEnd:null,input_type:node.type||'',readonly:!!node.readOnly,checked:typeof node.checked==='boolean'?node.checked:null})).filter(x=>x.value!==null||x.focused||x.checked!==null);
    // This separately scoped visual adapter never invents a readable label for
    // a blank tile/cell. Identity comes from the complete observed grid/table,
    // ordered geometry, clipped/painted rectangles and original frame binding.
    const htmlTableVisualTarget=(target,coordinate)=>{
      const canHit=([x,y])=>{const hit=document.elementFromPoint(x,y);return !!hit&&(hit===target||target.contains(hit));};
      if(location.href!=='https://www.jyshare.com/front-end/7688/'||width!==1280||height!==720||scrollX||scrollY)return null;
      const one=(s,r=document)=>r.querySelectorAll(s).length===1?r.querySelector(s):null;
      const box=n=>{const r=n.getBoundingClientRect();return [r.left,r.top,r.right,r.bottom];};
      const painted=n=>{
        if(!n?.checkVisibility({checkOpacity:true,checkVisibilityCSS:true})||n.closest('[inert],[aria-hidden=true]'))return false;
        for(let p=n;p;p=p.parentElement){const s=getComputedStyle(p),a=axisScale(p);
          if(s.visibility!=='visible'||Number(s.opacity)!==1||s.filter!=='none'||s.clipPath!=='none'||
             s.borderImageSource!=='none'||s.maskImage!=='none'||s.webkitMaskImage!=='none'||
             (s.maskBorderSource&&s.maskBorderSource!=='none')||
             !['::before','::after'].every(pseudo=>['none','normal'].includes(getComputedStyle(p,pseudo).content))||
             a.a!==1||a.b!==0||a.c!==0||a.d!==1)return false;}
        const r=n.getBoundingClientRect(),c=clipFor(n,true);
        return r.width>0&&r.height>0&&r.left>=c.left&&r.top>=c.top&&r.right<=c.right&&r.bottom<=c.bottom;
      };
      const surface=(n,allowedOverlay=null)=>{
        if(!painted(n))return false;const r=n.getBoundingClientRect();
        for(let x=r.left+1;x<r.right-1;x+=4)for(let y=r.top+1;y<r.bottom-1;y+=4){
          const h=document.elementFromPoint(x,y);
          if(!h||!(h===n||n.contains(h)||allowedOverlay&&(h===allowedOverlay||allowedOverlay.contains(h))))return false;
        }
        return true;
      };
      const color=value=>{
        const m=value.match(/^rgba?\((\d+),\s*(\d+),\s*(\d+)(?:,\s*([\d.]+))?\)$/);
        return m?[Number(m[1]),Number(m[2]),Number(m[3]),m[4]===undefined?1:Number(m[4])]:null;
      };
      const background=n=>{
        for(let p=n;p;p=p.parentElement){const s=getComputedStyle(p),c=color(s.backgroundColor);
          if(s.backgroundImage!=='none'||!c||c[3]!==0&&c[3]!==1)return null;
          if(c[3]===1)return c;
        }
        return [255,255,255,1];
      };
      const luminance=c=>c.slice(0,3).map(v=>v/255).map(v=>v<=.04045?v/12.92:((v+.055)/1.055)**2.4)
        .reduce((a,v,i)=>a+v*[.2126,.7152,.0722][i],0);
      const contrast=(a,b)=>{const x=luminance(a),y=luminance(b);return (Math.max(x,y)+.05)/(Math.min(x,y)+.05);};
      const border=n=>{const s=getComputedStyle(n),bg=background(n),selected=n.matches('.tg__cell_selected');
        if(!bg)return false;
        return ['Top','Right','Bottom','Left'].every(side=>{
          const c=color(s['border'+side+'Color']),expected=selected?[145,207,255]:[207,207,207];
          return parseFloat(s['border'+side+'Width'])===1&&s['border'+side+'Style']==='solid'&&c&&c[3]===1&&
            c.slice(0,3).every((v,i)=>v===expected[i])&&contrast(c,bg)>=1.15;
        });};
      const root=one('#content');if(!root||root.children.length!==1)return null;
      if(target.matches('.tg__cell')){
        const container=one('#content > .tg__container'),grid=one('#content > .tg__container > .tg__cells');
        const title=container&&one(':scope > h3.tg__title',container),size=container&&one(':scope > .tg__size > p',container);
        if(!container||container.children.length!==3||!grid||target.parentElement!==grid||grid.children.length!==100||
           !title||!size||!painted(title)||!painted(size)||clean(visibleText(title))!=='选择表格大小'||
           clean(title.textContent)!=='选择表格大小'||clean(visibleText(size))!=='1 x 1'||clean(size.textContent)!=='1 x 1'||
           document.querySelector('table.tbl,.tbl__area'))return null;
        const boxes=[];
        for(let i=0;i<100;i++){
          const tile=grid.children[i],r=Math.floor(i/10)+1,c=i%10+1;
          if(!tile.matches('div.tg__cell')||tile.children.length||clean(tile.textContent)||
             tile.getAttribute('row')!==String(r)||tile.getAttribute('col')!==String(c)||
             tile.classList.contains('tg__cell_selected')!==(i===0)||!surface(tile)||!border(tile))return null;
          const b=box(tile);boxes.push(b);
          if(Math.abs(b[1]-boxes[Math.floor(i/10)*10][1])>.5||Math.abs(b[0]-boxes[i%10][0])>.5||
             i%10&&boxes[i-1][2]>=b[0]||i>=10&&boxes[i-10][3]>=b[1])return null;
        }
        const position=[...grid.children].indexOf(target);
        return {adapter_id:'jyshare-html-table-visual-1',kind:'jyshare-table-size-cell',row:Math.floor(position/10)+1,
          column:position%10+1,rows:10,columns:10,matrix:null,geometry:boxes,known_menu_rect:null,
          source:'synchronized_browser_dom_geometry',full_viewport:true,occlusion_checked:true};
      }
      if(!target.matches('div.tbl__area[contenteditable=true]'))return null;
      const table=one('#content > .tbl__container > table.tbl'),container=table?.parentElement;
      const body=table&&one(':scope > tbody',table),cols=table&&one(':scope > colgroup',table);
      if(!table||!container||!body||!cols||table.children.length!==2||cols.children.length!==2||
         [...cols.children].some(n=>n.localName!=='col'||n.span!==1)||table.rows.length!==2||body.children.length!==2||
         table.querySelectorAll('.tbl__area').length!==4||document.querySelector('.tg__container')||!painted(table))return null;
      const siblingRoles=['table.tbl','div.cm','div.toolbar__horizontal-line','div.toolbar__vertical-line',
        'div.cm__open-btn','div.toolbar.toolbar_v','div.toolbar.toolbar_h'];
      if(container.children.length!==siblingRoles.length||[...container.children].some((n,i)=>!n.matches(siblingRoles[i])))return null;
      const contextMenu=container.children[1];
      if(!contextMenu.classList.contains('hidden')||contextMenu.checkVisibility({checkOpacity:true,checkVisibilityCSS:true}))return null;
      // The site's observed chevron is a sibling of the table and overlays the
      // last 25px of a selected cell. Permit only this exact helper footprint;
      // no arbitrary overlay, text-covered area or action coordinate is exempt.
      const menus=container.querySelectorAll(':scope > .cm__open-btn'),menu=menus.length===1?menus[0]:null;
      let overlay=null,menuBox=null;
      if(menu&&menu.checkVisibility({checkOpacity:true,checkVisibilityCSS:true})){
        const svg=one(':scope > svg.feather.feather-chevron-down',menu),poly=svg&&one(':scope > polyline',svg);
        if(!svg||!poly||menu.children.length!==1||svg.children.length!==1||clean(menu.textContent)||
           poly.getAttribute('points')!=='6 9 12 15 18 9'||!painted(menu))return null;
        menuBox=box(menu);if(Math.abs(menuBox[2]-menuBox[0]-25)>.1||Math.abs(menuBox[3]-menuBox[1]-25)>.1)return null;
        overlay=menu;
      }
      const geometry=[],matrix=[];let found=null,overlayCell=null;
      for(let r=0;r<2;r++){
        const row=table.rows[r];if(row.parentElement!==body||row.children.length!==2||row.cells.length!==2)return null;
        const values=[];
        for(let c=0;c<2;c++){
          const td=row.cells[c],area=one(':scope > div.tbl__area[contenteditable=true]',td);
          if(td.localName!=='td'||td.rowSpan!==1||td.colSpan!==1||!border(td)||!area||!area.isContentEditable||
             area.children.length||td.querySelectorAll('[contenteditable]').length!==1)return null;
          const other=[...td.children].filter(n=>n!==area);
          if(other.length>1||other.some(n=>!n.matches('div.tbl__resizer')||n.children.length||clean(n.textContent)))return null;
          const b=box(area);let helper=null;
          if(menuBox&&menuBox[0]>=b[2]-35&&menuBox[2]<=b[2]&&menuBox[1]>=b[1]&&menuBox[3]<=b[3]){
            if(overlayCell)return null;overlayCell=[r+1,c+1];helper=overlay;
            if(!area.classList.contains('tbl__area_selected')||document.activeElement!==area||
               Math.abs(b[2]-menuBox[2]-5)>1||Math.abs((menuBox[1]+menuBox[3]-b[1]-b[3])/2)>1)return null;
          }
          if(!surface(area,helper)||clean(visibleText(area))!==clean(area.textContent))return null;
          if(area.textContent){const style=getComputedStyle(area);
            const fg=color(style.webkitTextFillColor),bg=background(area);
            if(parseFloat(style.fontSize)<10||style.textTransform!=='none'||
               !fg||fg[3]!==1||!bg||contrast(fg,bg)<3)return null;}
          geometry.push(b);values.push(area.textContent);
          if(area===target)found={row:r+1,column:c+1};
          if(c&&Math.abs(b[1]-geometry[r*2][1])>.5||r&&Math.abs(b[0]-geometry[c][0])>.5||
             c&&geometry[r*2][2]>b[0]+.5||r&&geometry[c][3]>b[1]+.5)return null;
        }
        matrix.push(values);
      }
      if(!found||overlay&&!overlayCell||!canHit(coordinate))return null;
      return {adapter_id:'jyshare-html-table-visual-1',kind:'jyshare-table-editor-cell',...found,rows:2,columns:2,
        matrix,geometry,html:table.outerHTML,known_menu_rect:menuBox,source:'synchronized_browser_dom_geometry',full_viewport:true,occlusion_checked:true};
    };
  const targetIndex=nodes.indexOf(target);
  // A large, bold caption on a switched-off button can be legible below
  // the general prose threshold. Bind its ink and its unique group in the
  // same viewport. This does not change the full-page text inventory.
  const groupedButtonLabel = button => {
    if(!button.matches('button:enabled')||button.closest('[aria-disabled="true"],[inert]'))return null;
    const headings='legend,h1,h2,h3,h4,h5,h6,[role="heading"]';
    let group=button.parentElement;
    while(group&&group!==document.body&&!group.querySelector(headings))group=group.parentElement;
    if(!group||group===document.body)return null;
    const titles=group.querySelectorAll(headings),buttons=[...group.querySelectorAll('button')];
    if(titles.length!==1||buttons.length<2)return null;
    const heading=titles[0],groupText=clean(visibleText(heading)),headingRect=heading.getBoundingClientRect();
    if(!groupText||groupText!==clean(heading.textContent)||headingRect.bottom>button.getBoundingClientRect().top||
       !frameworkAreaExposed(headingRect,heading))return null;
    const walker=document.createTreeWalker(button,NodeFilter.SHOW_TEXT),leaves=[];
    for(let node=walker.nextNode();node;node=walker.nextNode())if(clean(node.textContent))leaves.push(node);
    const text=clean(leaves[0]?.textContent);
    if(!text||leaves.some(node=>clean(node.textContent)!==text))return null;
    if(buttons.some(other=>other!==button&&[other,...other.querySelectorAll('*')].some(
        node=>[...node.childNodes].some(child=>child.nodeType===Node.TEXT_NODE&&clean(child.textContent)===text))))return null;
    for(const node of leaves) {
      const owner=node.parentElement,style=getComputedStyle(owner);
      if(!owner.checkVisibility({checkOpacity:true,checkVisibilityCSS:true})||
         parseFloat(style.fontSize)<18||Number(style.fontWeight)<600||style.textTransform!=='none'||
         !frameworkLabelPaint(owner,style,2.2))continue;
      const range=document.createRange();range.selectNodeContents(node);
      const rects=[...range.getClientRects()];
      if(rects.length!==1)continue;
      const rect=rects[0];
      if(!exposedRect(rect,owner,clipFor(owner,true))||!frameworkAreaExposed(rect,owner))continue;
      return {kind:'rendered_grouped_button',text,group:groupText,
        text_bbox:[rect.left,rect.top,rect.right,rect.bottom],group_bbox:[headingRect.left,headingRect.top,headingRect.right,headingRect.bottom]};
    }
    return null;
  };
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
    for(const label of target.labels||[])addLabel('rendered_associated_label',frameworkLabelText(label));
    for(const id of (target.getAttribute('aria-labelledby')||'').split(/\s+/).filter(Boolean)) {
      const label=document.getElementById(id);
      if(label)addLabel('rendered_labelledby_text',label.matches('label.layui-form-label')?frameworkLabelText(label):visibleText(label));
    }
    // Bootstrap-style input groups sometimes have a visible addon rather than
    // an HTML-associated label. Accept only an unambiguous two-branch group;
    // proximity elsewhere in a form never establishes a label relationship.
    const adjacentInputGroupLabel=()=>{
      if(!target.matches('input,textarea,select')||target.readOnly||target.disabled||
         target.matches('input[type=hidden],input[type=range],input[type=color],input[type=file],input[type=checkbox],input[type=radio],input[type=button],input[type=submit],input[type=reset],input[type=image]'))return '';
      const parent=target.parentElement;
      let group,label,branch,uploadLabel=null,unitCompanions=[],fieldCompanions=[],valueButton=null;
      if(parent?.matches('.input-group')) {
        group=parent;
        if(group.children.length!==2||group.querySelector('.input-group'))return '';
        const labels=group.querySelectorAll('.input-group-text');
        if(labels.length!==1)return '';
        label=labels[0];branch=label.parentElement===group?label:label.parentElement;
        if(!label.matches('span')||label.children.length||branch.parentElement!==group)return '';
        if(branch!==label&&(!branch.matches('.input-group-prepend,.input-group-append')||branch.children.length!==1))return '';
      } else if(target.matches('.form-control')&&parent?.parentElement?.matches('form.form-horizontal .row,form.form-horizontal .form-group')) {
        group=parent.parentElement;
        if(group.children.length!==2||parent.children.length!==1||
           [...parent.childNodes].some(n=>n.nodeType===Node.TEXT_NODE&&clean(n.textContent)))return '';
        label=group.firstElementChild;branch=label;
        if(label===parent||!label.matches('label.control-label,label.col-form-label')||label.children.length||
           label.hasAttribute('for'))return '';
      } else if(parent?.matches('.layui-input-block,.layui-input-inline')&&parent.parentElement?.matches('.layui-form-item')) {
        group=parent.parentElement;
        if(parent.children.length!==1||parent.firstElementChild!==target)return '';
        const labels=[...group.children].filter(e=>e.matches('label.layui-form-label'));
        if(labels.length!==1)return '';
        label=labels[0];branch=label;
        uploadLabel=frameworkUploadLabel(label);
        if(label.children.length&&!uploadLabel)return '';
        // A framework's plain, noninteractive inline hint is a separate third
        // branch. It never supplies the target name. All other extra branches
        // remain ambiguous, including a second control or unrelated prose.
        const hints=[...group.children].filter(e=>e!==label&&e!==parent);
        if(hints.length>1||hints.some(e=>!e.matches('div.layui-form-mid.layui-word-aux')||
           e.children.length||e.hasAttribute('onclick')||e.hasAttribute('role')||
           e.hasAttribute('tabindex')||getComputedStyle(e).cursor==='pointer'))return '';
        if(label.hasAttribute('for')&&label.control!==target)return '';
        if([...parent.childNodes].some(n=>n.nodeType===Node.TEXT_NODE&&clean(n.textContent)))return '';
      } else if(parent?.matches('div.layui-input-res')&&parent.parentElement?.matches('div.layui-form-resItem')) {
        group=parent.parentElement;
        if(group.children.length!==4||parent.children.length!==2||
           ![...parent.children].some(e=>e!==target&&e.matches('label.res-label')&&!e.children.length))return '';
        const labels=[...group.children].filter(e=>e.matches('label.layui-form-label'));
        const selects=[...group.children].filter(e=>e.matches('select'));
        const renderers=[...group.children].filter(e=>e.matches('div.layui-form-select'));
        if(labels.length!==1||selects.length!==1||renderers.length!==1)return '';
        label=labels[0];branch=label;
        if(label.children.length||label.control===target||label.hasAttribute('for')&&label.control!==target)return '';
        const backing=selects[0],units=[...renderers[0].querySelectorAll('input')];
        if(backing.getClientRects().length||backing.selectedOptions.length!==1||units.length!==1||
           !units[0].readOnly||clean(units[0].value)!==clean(backing.selectedOptions[0].textContent))return '';
        unitCompanions=[backing,units[0]];
        const hint=parent.querySelector('label.res-label'),hs=getComputedStyle(hint),hr=hint.getBoundingClientRect(),tr=target.getBoundingClientRect();
        if(target.value===''&&clean(hint.textContent).length<=40&&
           frameworkColor(hs.backgroundColor)?.[3]===0&&hs.backgroundImage==='none'&&hs.boxShadow==='none'&&hs.filter==='none'&&
           ['Top','Right','Bottom','Left'].every(side=>parseFloat(hs['border'+side+'Width'])===0)&&
           ['::before','::after'].every(p=>['none','normal'].includes(getComputedStyle(hint,p).content))&&
           hr.left>=tr.left&&hr.right<=tr.right&&hr.top>=tr.top&&hr.bottom<=tr.bottom&&hr.width<=0.8*tr.width)
          fieldCompanions=[hint]; // Transparent text hint over its own empty field.
      } else if(parent?.children.length===2) {
        // A direct, isolated label/input pair (including a leaf Layui prefix)
        // has no competing target. The shared paint/geometry proof below still
        // applies; arbitrary nearby prose and multiple controls stay unknown.
        let labels=[...parent.children].filter(e=>e!==target&&
          (e.matches('label')||e.matches('div.layui-input-prefix'))&&!e.children.length);
        if(!labels.length) {
          // Bare input paired with a value-labeled button: the button's painted
          // text names the group (e.g. an unlabeled search box next to a
          // "搜索" submit). The button itself is a control and is excluded
          // from the group scan below; the same paint proof still applies.
          const others=[...parent.children].filter(e=>e!==target&&!e.children.length&&
            (e.matches('input[type=button],input[type=submit]')||e.matches('button')));
          if(others.length===1&&others[0].getClientRects().length) {
            const button=others[0];
            if(button.matches('input')) {
              if(clean(button.value)&&nativeValueVisible(button,true)) {valueButton=button;labels=[button];}
            } else if(clean(button.textContent))labels=[button];
          }
        }
        if(labels.length!==1)return '';
        group=parent;label=labels[0];branch=label;
        if(label.control===target)return ''; // Keep native association provenance.
        if(label.hasAttribute('for')&&label.control!==target)return '';
      } else return '';
      const controls=[...group.querySelectorAll('input,textarea,select,button,[contenteditable],[role=textbox],[role=combobox],[role=spinbutton],[role=button]')]
        .filter(e=>(!uploadLabel||e!==uploadLabel.button&&e!==uploadLabel.file)&&!unitCompanions.includes(e)&&e!==valueButton);
      if(controls.length!==1||controls[0]!==target)return '';
      const hasOwnText=node=>[...node.childNodes].some(child=>child.nodeType===Node.TEXT_NODE&&clean(child.textContent));
      if(hasOwnText(group)||(branch!==label&&hasOwnText(branch)))return '';
      // Full original text must survive the existing per-grapheme clipping and
      // occlusion checks. Partial visible fragments cannot name the control.
      const source=uploadLabel?.source||(valueButton?clean(valueButton.value):clean(label.textContent)),
            text=uploadLabel?.text||(valueButton?source:clean(visibleText(label)));
      if(!source||text!==source)return '';
      const style=getComputedStyle(label);
      if(parseFloat(style.fontSize)<10||style.textTransform!=='none'||
         !frameworkLabelPaint(label)||
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
      const stacked=group.matches('.layui-form-item.layui-form-text')&&target.tagName==='TEXTAREA'&&
        a.bottom<=b.top+1&&b.top-a.bottom<=20&&Math.abs(a.left-b.left)<=16&&
        Math.min(a.right,b.right)-Math.max(a.left,b.left)>=0.8*Math.min(a.width,b.width);
      if(!stacked&&(gap < -1||gap>16||overlap<0.8*Math.min(a.height,b.height)||
         Math.abs((a.top+a.bottom-b.top-b.bottom)/2)>8))return '';
      // The later-painted neighbor can own that shared border's hit point.
      // Exclude only their measured <=1px intersection from box probes; all
      // original label graphemes above must still be fully exposed.
      const unsharedBox=(rect,other)=>{
        let left=rect.left,right=rect.right;
        if(gap<0) {if(left<other.left)right=other.left;else left=other.right;}
        return {left,right,top:rect.top,bottom:rect.bottom,width:right-left,height:rect.height};
      };
      const stackedBox=(rect,other)=>{
        const top=rect.top>=other.top?Math.max(rect.top,other.bottom):rect.top;
        const bottom=rect.top<other.top?Math.min(rect.bottom,other.top):rect.bottom;
        return {left:rect.left,right:rect.right,top,bottom,width:rect.width,height:bottom-top};
      };
      const labelBox=stacked?stackedBox(a,b):unsharedBox(a,b),targetBox=stacked?stackedBox(b,a):unsharedBox(b,a);
      if(!exposedRect(labelBox,label,clipFor(label))||!exposedRect(targetBox,target,clipFor(target)))return '';
      if(!frameworkAreaExposed(labelBox,label)||!frameworkAreaExposed(targetBox,target,fieldCompanions))return '';
      const shared={left:Math.max(a.left,b.left),right:Math.min(a.right,b.right),
        top:Math.max(a.top,b.top),bottom:Math.min(a.bottom,b.bottom)};
      if(shared.right>shared.left&&shared.bottom>shared.top&&!frameworkAreaExposed(shared,label,[target]))return '';
      // The generic 3x3 hit probes can miss an overlay between the center and
      // edge of a wide input. This new inference additionally checks its area
      // on a 4 CSS-pixel grid; no existing visibility rule is relaxed.
      for(let x=targetBox.left+1;x<targetBox.right;x+=4)for(let y=targetBox.top+1;y<targetBox.bottom;y+=4) {
        if(!textHit(x,y,target))return '';
      }
      return text;
    };
    const adjacentText=adjacentInputGroupLabel();
    const frameworkTarget=target.parentElement?.matches('.layui-input-block,.layui-input-inline')&&
      target.parentElement.parentElement?.matches('.layui-form-item');
    // An explicit framework label/placeholder must not bypass its stricter
    // complete-field checks after the adjacent inference rejected the surface.
    if(frameworkTarget&&!adjacentText)labelSources.length=0;
    addLabel('rendered_adjacent_input_group_label',adjacentText);
    if((!frameworkTarget||adjacentText)&&nativeValueVisible(target,true)) {
      if(target.tagName==='SELECT')addLabel('visible_selected_option',[...target.selectedOptions].map(o=>o.label||o.textContent).join(' '));
      else if(target.matches('input,textarea'))addLabel(target.value?'visible_native_value':'visible_placeholder',target.value||target.placeholder);
    }
    if(!labelSources.length&&e.enabled&&canHit(coordinate)) {
      const grouped=groupedButtonLabel(target);if(grouped)labelSources.push(grouped);
    }
    targetInfo={element_id:e.element_id,coordinate,hit_valid:canHit(coordinate),bbox:e.bbox,text:e.text,enabled:e.enabled,
      focused:document.activeElement===target,value:typeof target.value==='string'?target.value:null,
      visible_label_evidence:labelSources,visual_target_evidence:htmlTableVisualTarget(target,coordinate)};
  }
  const visiblePieces=[];
  const walker=document.createTreeWalker(document.body,NodeFilter.SHOW_TEXT);
  for(let node=walker.nextNode();node;node=walker.nextNode()) {
    const parent=node.parentElement;
    if(!parent||parent.closest('script,style,noscript,template')||!parent.checkVisibility({checkOpacity:true,checkVisibilityCSS:true}))continue;
    const text=clean(visibleText(node));if(text)visiblePieces.push(text);
  }
  for(const node of nodes) {
    if(!node.matches('input,textarea')||node.type==='range'||node.type==='file')continue;
    if(node.type==='password') {
      // A proven empty placeholder is painted text, not a password value.
      // Once typing masks the field, neither value nor placeholder is exposed.
      if(node.value===''&&node.placeholder&&nativeValueVisible(node,true))visiblePieces.push(node.placeholder);
      continue;
    }
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
    let tableEvidence=null;
    if('html_table_matrix' in condition&&condition.selector==='#content > .tbl__container > table.tbl'&&
       location.href==='https://www.jyshare.com/front-end/7688/'&&node.matches('table.tbl')){
      const area=node.querySelector(':scope > tbody > tr:first-child > td:first-child > div.tbl__area[contenteditable=true]');
      if(area){const a=area.getBoundingClientRect();tableEvidence=htmlTableVisualTarget(area,
        [Math.floor((a.left+a.right-1)/2),Math.floor((a.top+a.bottom-1)/2)]);}
    }
    return {selector:condition.selector,index:condition.index||0,
      visible:(!node.checkVisibility||node.checkVisibility({checkOpacity:true,checkVisibilityCSS:true}))&&
        style.visibility==='visible'&&rect.width>0&&rect.height>0&&rect.left>=0&&rect.top>=0&&rect.right<=width&&rect.bottom<=height&&
        !!hit&&(hit===node||node.contains(hit)),
      text:clean(visibleText(node)),target_text:name(node),value:node.matches('input,textarea,select')&&typeof node.value==='string'?node.value:null,value_visible:nativeValueVisible(node),
      display_value:node.tagName==='SELECT'?[...node.selectedOptions].map(option=>clean(option.label||option.textContent)).join(' '):
        (typeof node.value==='string'?node.value:null),
      // Only SELECT display_value is rendered text; input/textarea display_value
      // is the DOM value itself and can never prove screenshot visibility.
      display_source:node.tagName==='SELECT'?'rendered-option-text':'dom-value',
      checked:control?.matches('input[type=radio],input[type=checkbox]')?control.checked:null,
      disabled:node.matches(':disabled')||node.getAttribute('aria-disabled')==='true',
      bbox:[rect.left,rect.top,rect.right,rect.bottom],...('html_table_matrix' in condition?{html_table_evidence:tableEvidence}:{}),
      ...('placeholder_png_text' in condition?{placeholder_image:
        location.href==='https://www.jyshare.com/front-end/9355/'&&condition.selector==='#placeholderResult > img.holderjs-placeholder'&&
        document.querySelectorAll(condition.selector).length===1&&node.matches('img.holderjs-placeholder')&&node.parentElement.children.length===1&&
        node.src.startsWith('data:image/png;base64,')&&node.src.length<=2000000?
        {src:node.src,complete:node.complete,natural_width:node.naturalWidth,natural_height:node.naturalHeight}:null}:{} )};
  });
  // This is a deliberately narrow exclusion proof, not an image classifier.
  // Keep every source and loaded flag in the full snapshot. Only explicitly
  // decorative, non-hit-testable images can ever receive a pixel exclusion.
  const protectedNodes=[target,...assertions.filter(c=>c.selector).map(c=>document.querySelectorAll(c.selector)[c.index||0]),
    ...protected_selectors.flatMap(s=>[...document.querySelectorAll(s)])].filter(Boolean);
  const intersects=(a,b)=>Math.min(a[2],b[2])>Math.max(a[0],b[0])&&Math.min(a[3],b[3])>Math.max(a[1],b[1]);
  const rawBox=n=>{const r=n.getBoundingClientRect();return [r.left,r.top,r.right,r.bottom];};
  const textRects=[];
  const textWalker=document.createTreeWalker(document.body||document.documentElement,NodeFilter.SHOW_TEXT);
  while(textWalker.nextNode()) {
    const n=textWalker.currentNode,p=n.parentElement;
    if(!clean(n.textContent)||!p||p.closest('script,style,noscript,template')||
       !p.checkVisibility({checkOpacity:true,checkVisibilityCSS:true}))continue;
    const range=document.createRange();range.selectNodeContents(n);
    for(const r of range.getClientRects())if(r.width&&r.height)textRects.push([r.left,r.top,r.right,r.bottom]);
  }
  const captureImages=[];
  for(const image of document.images) {
    const r=image.getBoundingClientRect();
    if(!image.checkVisibility({checkOpacity:true,checkVisibilityCSS:true})||r.width<=0||r.height<=0||
       r.right<=0||r.bottom<=0||r.left>=width||r.top>=height)continue;
    if(!observer.ids.has(image))observer.ids.set(image,`e_${observer.next++}`);
    if(unrelatedTransforms.has(image)) {
      captureImages.push({element_id:observer.ids.get(image),bbox:rawBox(image),
        src:image.getAttribute('src')||'',current_src:image.currentSrc||'',complete:image.complete,
        natural_width:image.naturalWidth,natural_height:image.naturalHeight,eligible:false,
        exclusion_reasons:['transformed_image_pixels_must_remain_exact'],geometry_proof:unrelatedTransforms.get(image)});
      continue;
    }
    const b=rawBox(image),reasons=[],s=getComputedStyle(image),clip=clipFor(image);
    if(image.getAttribute('alt')!==''||image.getAttribute('aria-hidden')!=='true'||
       !['presentation','none'].includes(image.getAttribute('role'))||s.pointerEvents!=='none'||
       image.hasAttribute('title')||image.hasAttribute('aria-label')||image.hasAttribute('aria-labelledby'))reasons.push('not_explicitly_decorative');
    if(!image.complete||image.naturalWidth<=0||image.naturalHeight<=0)reasons.push('image_not_loaded');
    // Image exclusions have their own overlap/unbounded-paint proof below.
    // The border-only proof is deliberately independent and computed later.
    if(!b.every(Number.isInteger)||r.left<0||r.top<0||r.right>width||r.bottom>height||
       r.left<clip.left||r.top<clip.top||r.right>clip.right||r.bottom>clip.bottom)reasons.push('clipped_or_fractional_geometry');
    for(let p=image;p;p=p.parentElement) {
      const a=getComputedStyle(p),scale=axisScale(p);
      if(p.matches('a,button,input,textarea,select,label,summary,figure,[tabindex],[contenteditable=true],[role=button],[role=link],[role=img]')||
         [...p.attributes].some(x=>/^on/i.test(x.name))||a.cursor==='pointer')reasons.push('interactive_or_semantic_ancestor');
      if(a.transform!=='none'||scale.a!==1||scale.b!==0||scale.c!==0||scale.d!==1||a.filter!=='none'||
         a.clipPath!=='none'||a.maskImage!=='none'||Number(a.opacity)!==1||a.mixBlendMode!=='normal'||
         a.boxShadow!=='none'||a.textShadow!=='none'||a.borderImageSource!=='none'||
         (parseFloat(a.outlineWidth)>0&&a.outlineStyle!=='none')||
         !['::before','::after'].every(pseudo=>['none','normal'].includes(getComputedStyle(p,pseudo).content)))reasons.push('unsupported_paint');
    }
    if(protectedNodes.some(n=>n===image||n.contains(image)||image.contains(n)||intersects(b,rawBox(n))))reasons.push('task_or_result_related');
    if(textRects.some(t=>intersects(b,t))||records.some((e,i)=>nodes[i]!==image&&!nodes[i].contains(image)&&
       (e.clickable||e.inputable||e.element_type==='image'||e.element_type==='window')&&intersects(b,e.bbox)))reasons.push('overlaps_text_or_control');
    // UI-tree filtering and hit tests cannot exclude pointer-transparent canvas,
    // SVG, or blank painted overlays. Unknown overlapping DOM regions therefore
    // disqualify the entire image exclusion, including between the hit samples.
    const unknownPaintOverlaps=[...document.querySelectorAll('*')].filter(n=>n!==image&&!n.contains(image)&&
      !image.contains(n)&&n.checkVisibility({checkOpacity:true,checkVisibilityCSS:true})&&
      intersects(b,rawBox(n))).map(n=>({tag:n.localName,id:n.id||'',bbox:rawBox(n)}));
    if(unknownPaintOverlaps.length)reasons.push('unknown_overlapping_paint');
    // Border boxes do not bound shadows, pseudo-elements, SVG overflow or
    // opaque custom renderers. Do not guess their paint extents from samples.
    const unboundedPaintSources=[];
    for(const n of document.querySelectorAll('*')) {
      if(n===image||n.contains(image)||!n.checkVisibility({checkOpacity:true,checkVisibilityCSS:true}))continue;
      const paint=getComputedStyle(n),effects={box_shadow:paint.boxShadow,text_shadow:paint.textShadow,
        filter:paint.filter,backdrop_filter:paint.backdropFilter||'none',border_image:paint.borderImageSource,
        outline:parseFloat(paint.outlineWidth)>0?paint.outlineStyle:'none',reflection:paint.webkitBoxReflect||'none',
        before:getComputedStyle(n,'::before').content,after:getComputedStyle(n,'::after').content};
      const opaque=n instanceof SVGElement||!!n.shadowRoot||n.localName.includes('-');
      if(opaque||Object.entries(effects).some(([key,value])=>!['none','normal'].includes(value)))
        unboundedPaintSources.push({tag:n.localName,id:n.id||'',bbox:rawBox(n),opaque,effects});
    }
    if(unboundedPaintSources.length)reasons.push('unbounded_external_paint');
    const hitSamples=[];
    for(const x of [r.left+.5,(r.left+r.right)/2,r.right-.5])for(const y of [r.top+.5,(r.top+r.bottom)/2,r.bottom-.5]) {
      const hit=document.elementFromPoint(x,y),ancestor=!!hit&&hit.contains(image);
      hitSamples.push({point:[x,y],hit_tag:hit?.localName||null,hit_id:hit?.id||'',ancestor});
      if(!ancestor)reasons.push('covered_or_unknown_hit');
    }
    captureImages.push({element_id:observer.ids.get(image),bbox:b,src:image.getAttribute('src')||'',current_src:image.currentSrc||'',
      complete:image.complete,natural_width:image.naturalWidth,natural_height:image.naturalHeight,
      exclusion_basis:{schema_version:'webcollect-decorative-image-basis-1',
        attributes:Object.fromEntries(['alt','aria-hidden','role','title','aria-label','aria-labelledby'].map(k=>[k,image.getAttribute(k)])),
        pointer_events:s.pointerEvents,clip_bbox:[clip.left,clip.top,clip.right,clip.bottom],hit_samples:hitSamples,
        protected_regions:protectedNodes.map(n=>({bbox:rawBox(n),contains_image:n===image||n.contains(image),inside_image:image.contains(n)})),
        unknown_paint_overlaps:unknownPaintOverlaps,
        unbounded_paint_sources:unboundedPaintSources,
        ancestor_exclusions:[...new Set(reasons.filter(r=>['interactive_or_semantic_ancestor','unsupported_paint'].includes(r)))],
        protected_overlap:reasons.includes('task_or_result_related'),
        text_or_control_overlap:reasons.includes('overlaps_text_or_control')},
      eligible:reasons.length===0,exclusion_reasons:[...new Set(reasons)]});
  }
  // Explicitly peripheral silent video may repaint inside its own box. This
  // is a single-frame synchrony exception, never an action-effect proof.
  const captureMedia=[];
  for(const video of document.querySelectorAll('aside video,[role="complementary"] video,video[aria-hidden="true"]')) {
    if(!video.checkVisibility({checkOpacity:true,checkVisibilityCSS:true}))continue;
    const b=rawBox(video),c=getComputedStyle(video),clip=clipFor(video);
    const controls=[...document.querySelectorAll('a[href],button,input,select,textarea,summary,[tabindex],[contenteditable=true],[role=button],[role=link]')];
    const guards=[...protectedNodes,...controls].filter(n=>n!==video&&n.checkVisibility({checkOpacity:true,checkVisibilityCSS:true}));
    const guardBoxes=guards.map(rawBox).concat(textRects.map(r=>Array.isArray(r)?r:[r.left,r.top,r.right,r.bottom]));
    const unknownPaint=[...document.querySelectorAll('*')].some(n=>{
      if(n===video||n.contains(video)||!n.checkVisibility({checkOpacity:true,checkVisibilityCSS:true}))return false;
      const s=getComputedStyle(n);
      return intersects(b,rawBox(n))||s.boxShadow!=='none'||s.filter!=='none'||!!n.shadowRoot||n instanceof SVGElement||
        !['::before','::after'].every(p=>['none','normal'].includes(getComputedStyle(n,p).content));
    });
    const hits=[];
    for(const x of [b[0]+.5,(b[0]+b[2])/2,b[2]-.5])for(const y of [b[1]+.5,(b[1]+b[3])/2,b[3]-.5])
      hits.push(document.elementFromPoint(x,y)===video);
    const eligible=!unknownPaint&&b.every(Number.isInteger)&&b[0]>=0&&b[1]>=0&&b[2]<=width&&b[3]<=height&&
      b[0]>=clip.left&&b[1]>=clip.top&&b[2]<=clip.right&&b[3]<=clip.bottom&&
      video!==target&&!video.controls&&!video.hasAttribute('tabindex')&&!video.hasAttribute('onclick')&&
      !video.closest('a,button,label,figure,[contenteditable=true]')&&video.readyState>=2&&
      c.transform==='none'&&c.filter==='none'&&c.boxShadow==='none'&&c.borderRadius==='0px'&&
      !video.hasAttribute('title')&&!video.hasAttribute('aria-label')&&!video.hasAttribute('aria-labelledby')&&
      guardBoxes.every(box=>!intersects(b,box))&&hits.every(Boolean);
    captureMedia.push({kind:'peripheral_video',bbox:b,src:video.currentSrc,ready:video.readyState>=2,
      eligible,proof:{schema_version:'webcollect-peripheral-video-1',peripheral:true,
        controls:video.controls,protected_boxes:guardBoxes,hit_samples:hits,
        geometry_and_style_clear:!!eligible},actions_supported:false});
  }
  // Conservative paint evidence: plain integral non-task border boxes only.
  // Text, task targets, focused/selected controls and unknown paint stay exact.
  const paintBorders=[];
  const unknownBorderPaint=[...document.querySelectorAll('*')].some(n=>{
    if(!n.checkVisibility({checkOpacity:true,checkVisibilityCSS:true}))return false;
    const c=getComputedStyle(n);
    return n instanceof SVGElement||!!n.shadowRoot||n.localName.includes('-')||
      c.boxShadow!=='none'||c.filter!=='none'||c.textShadow!=='none'||
      !['::before','::after'].every(p=>['none','normal'].includes(getComputedStyle(n,p).content));
  });
  for(const node of document.querySelectorAll('input,button,select,textarea')) {
    const b=rawBox(node),c=getComputedStyle(node);
    if(unknownBorderPaint||!b.every(Number.isInteger)||!node.checkVisibility({checkOpacity:true,checkVisibilityCSS:true})||
       node===document.activeElement||node.checked||node.disabled||
       protectedNodes.some(n=>n===node||n.contains(node)||node.contains(n))||
       c.transform!=='none'||c.filter!=='none'||c.boxShadow!=='none'||c.borderImageSource!=='none'||
       c.borderRadius!=='0px'||c.outlineStyle!=='none'||c.backgroundImage!=='none'||
       !['Top','Right','Bottom','Left'].every(side=>c['border'+side+'Style']==='solid'&&c['border'+side+'Width']==='1px')||
       !['::before','::after'].every(pseudo=>['none','normal'].includes(getComputedStyle(node,pseudo).content)))continue;
    const edges=[[b[0],b[1],b[2],b[1]+1],[b[0],b[3]-1,b[2],b[3]],
                 [b[0],b[1],b[0]+1,b[3]],[b[2]-1,b[1],b[2],b[3]]];
    if(edges.some(edge=>textRects.some(t=>intersects(edge,t))))continue;
    if([...document.querySelectorAll('*')].some(n=>n!==node&&!n.contains(node)&&
       n.checkVisibility({checkOpacity:true,checkVisibilityCSS:true})&&edges.some(edge=>intersects(edge,rawBox(n)))))continue;
    const hits=edges.every(edge=>{
      for(let x=edge[0];x<edge[2];x++)for(let y=edge[1];y<edge[3];y++)
        if(document.elementFromPoint(x+.5,y+.5)!==node)return false;
      return true;
    });
    if(hits)paintBorders.push({bbox:b,edges,tag:node.localName,colors:['Top','Right','Bottom','Left'].map(side=>c['border'+side+'Color'])});
  }
  const captureControls=nodes.map((node,i)=>{
    const parts=[];let n=node;
    while(n&&n.nodeType===1){
      const siblings=n.parentElement?[...n.parentElement.children].filter(s=>s.localName===n.localName):[n];
      parts.unshift(n.localName+':nth-of-type('+(siblings.indexOf(n)+1)+')');n=n.parentElement;
    }
    return {element_id:records[i].element_id,selector:parts.join(' > '),index:0,tag:node.localName,href:node.localName==='a'?node.href:null,input_type:node.type||'',form_index:node.form?[...document.forms].indexOf(node.form):null,
      options:node.localName==='select'?[...node.options].map(o=>({value:o.value,label:clean(o.label),disabled:o.disabled})):[]};
  });
  return {url:location.href,title:document.title,screen_resolution:[width,height],device_pixel_ratio:devicePixelRatio,
    capture_readiness:{schema_version:'webcollect-capture-readiness-1',document_ready:document.readyState,
      fonts_ready:!document.fonts||document.fonts.status==='loaded',images_ready:captureImages.every(i=>i.complete&&i.natural_width>0&&i.natural_height>0)},
    unrelated_transform_proofs:transformProofs, capture_images:captureImages,capture_media:captureMedia,paint_borders:paintBorders,capture_controls:captureControls,
    document_identity:{url_without_fragment:location.href.split('#')[0],performance_time_origin:performance.timeOrigin},
    scroll:[scrollX,scrollY],elements:records,values,target:targetInfo,
    visible_text:visiblePieces.join('\n'),text_blocks:textBlocks,
    embedded_frames:nodes.map((node,i)=>node.matches('iframe,frame')?{
      element_id:records[i].element_id,bbox:records[i].bbox,title:node.getAttribute('title')||'',
      src:node.getAttribute('src')||'',subtree:'opaque_unread',task_actions_supported:false,
      focused:document.activeElement===node}:null).filter(Boolean),
    ...(assertions.length?{assertion_targets:assertionTargets}:{} )};
}
