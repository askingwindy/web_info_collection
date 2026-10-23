/* Read-only DOM advice. No content/style/attribute/resource/action mutation. */
({settings = {}, instruction = '', operation = {}} = {}) => {
  const width=innerWidth,height=innerHeight,viewportArea=width*height;
  const clean=s=>(s||'').replace(/\s+/g,' ').trim();
  const adWords=/广告|推广|扫码|领取优惠|限时优惠|立即下载|advertis|promotion|sponsor/i;
  const forbiddenAction=/登录|注册|同意|接受|支付|购买|下载|报名|订阅|sign.?in|log.?in|accept|agree|buy|download|subscribe/i;
  const safeClose=/^(?:关闭|关闭广告|关闭推广|关闭弹窗|暂不|稍后|close|dismiss|[×✕✖ｘxX])$/i;
  const round=r=>({x:Math.round(r.left*100)/100,y:Math.round(r.top*100)/100,
    width:Math.round(r.width*100)/100,height:Math.round(r.height*100)/100});
  const styleVisible=node=>{
    if(!node||!node.isConnected)return false;
    for(let n=node;n&&n.nodeType===1;n=n.parentElement){
      const s=getComputedStyle(n);
      if(s.display==='none'||s.visibility!=='visible'||Number(s.opacity)===0)return false;
    }
    return true;
  };
  const intersect=r=>Math.max(0,Math.min(width,r.right)-Math.max(0,r.left))*
    Math.max(0,Math.min(height,r.bottom)-Math.max(0,r.top));
  const hitPoint=node=>{
    if(!styleVisible(node))return null;
    for(const r of node.getClientRects()){
      const l=Math.max(0,r.left),rr=Math.min(width,r.right),t=Math.max(0,r.top),b=Math.min(height,r.bottom);
      if(rr-l<2||b-t<2)continue;
      for(const [fx,fy] of [[.5,.5],[.15,.5],[.85,.5],[.5,.15],[.5,.85]]){
        const x=l+(rr-l)*fx,y=t+(b-t)*fy,hit=document.elementFromPoint(x,y);
        if(hit&&(hit===node||node.contains(hit)))return [x,y];
      }
    }
    return null;
  };
  const selectorFor=node=>{
    if(!node||node.nodeType!==1)return null;
    if(node.id){
      const id='#'+CSS.escape(node.id);
      if(document.querySelectorAll(id).length===1)return id;
    }
    const path=[];
    for(let n=node;n&&n.nodeType===1;n=n.parentElement){
      const tag=n.localName;
      const siblings=n.parentElement?[...n.parentElement.children].filter(s=>s.localName===tag):[n];
      path.unshift(tag+':nth-of-type('+(siblings.indexOf(n)+1)+')');
      const result=path.join(' > ');
      if(document.querySelectorAll(result).length===1)return result;
    }
    return null;
  };
  const rectExposed=(r,owner)=>{
    if(r.left<0||r.top<0||r.right>width||r.bottom>height||r.width<=0||r.height<=0)return false;
    for(let n=owner.parentElement;n&&n!==document.body&&n!==document.documentElement;n=n.parentElement){
      const s=getComputedStyle(n),b=n.getBoundingClientRect();
      if(/hidden|clip|auto|scroll/.test(s.overflowX)&&(r.left<b.left||r.right>b.right))return false;
      if(/hidden|clip|auto|scroll/.test(s.overflowY)&&(r.top<b.top||r.bottom>b.bottom))return false;
    }
    const insetX=Math.min(1,r.width/4),insetY=Math.min(1,r.height/4);
    return [r.left+insetX,(r.left+r.right)/2,r.right-insetX].every(x=>
      [r.top+insetY,(r.top+r.bottom)/2,r.bottom-insetY].every(y=>{
        const hit=document.elementFromPoint(x,y);
        return !!hit&&(hit===owner||hit.contains(owner));
      }));
  };
  const textEvidence=node=>{
    const empty={text:'',complete_visible_lines:0,line_texts:[]};
    if(!styleVisible(node)||!intersect(node.getBoundingClientRect()))return empty;
    const walker=document.createTreeWalker(node,NodeFilter.SHOW_TEXT);
    const segmenter=new Intl.Segmenter(undefined,{granularity:'grapheme'});
    let n,answer='',examined=0;const lines=new Map();
    while((n=walker.nextNode())&&examined<1800){
      const owner=n.parentElement;
      if(!styleVisible(owner)||owner.closest('script,style,noscript,template'))continue;
      const range=document.createRange();
      for(const g of segmenter.segment(n.textContent)){
        examined++;if(examined>1800)break;
        range.setStart(n,g.index);range.setEnd(n,g.index+g.segment.length);
        const boxes=[...range.getClientRects()].filter(r=>r.width>0&&r.height>0);
        const exposed=boxes.length&&boxes.every(r=>rectExposed(r,owner));
        if(exposed)answer+=g.segment;
        else if(answer&&!/\s$/.test(answer))answer+=' ';
        if(g.segment.trim())for(const box of boxes){
          const key=Math.round(box.top*10)/10;
          if(!lines.has(key))lines.set(key,{text:'',all_exposed:true});
          const line=lines.get(key);line.text+=g.segment;line.all_exposed&&=!!exposed;
        }
      }
      answer+=' ';
    }
    const complete=[...lines.entries()].filter(([top,line])=>line.all_exposed&&line.text.replace(/\s/g,'').length>=12);
    return {text:clean(answer),complete_visible_lines:complete.length,line_texts:complete.slice(0,5).map(([top,line])=>({top,text:line.text}))};
  };
  const visibleText=node=>textEvidence(node).text;
  const ignored=node=>!!node.closest('nav,header,footer,aside,[role="navigation"],[role="complementary"],[role="dialog"],[aria-modal="true"],[data-ad],.advertisement,.advert,.ads,.ad-banner');
  let planned=null;
  try{if(operation.selector)planned=document.querySelectorAll(operation.selector)[operation.index||0];}catch(_){}
  const plannedPoint=hitPoint(planned);
  const fields=[...document.querySelectorAll('input:not([type="hidden"]),textarea,select')]
    .filter(n=>hitPoint(n)&&!ignored(n)&&!n.closest('[role="dialog"],[aria-modal="true"]'));
  const calculationButtons=[...document.querySelectorAll('button,[role="button"],input[type="button"],input[type="submit"]')]
    .filter(n=>hitPoint(n)&&!ignored(n)&&/^(?:计算|换算|转换|开始计算|计算结果|calculate|convert)$/i.test(clean(n.value||n.textContent)));
  const visibleOutputs=[...document.querySelectorAll('output,[role="status"]')]
    .filter(n=>hitPoint(n)&&!ignored(n)&&/\d/.test(clean(n.value||n.textContent)));
  const calculationForm=fields.some(n=>n.localName==='input'&&/\d/.test(n.value||''))&&calculationButtons.length>0&&visibleOutputs.length>0;
  const actualForm=fields.length>0&&(
    fields.some(n=>/number|date|range/.test(n.type||''))||
    fields.length>=2||fields.some(n=>n.localName==='textarea')||calculationForm);
  const reference={found:false,kind:null,reason:'No exposed structured reference fields/table verified.',evidence:[]};
  const contentRegions=[...document.querySelectorAll('main,article,[role="main"]')];
  const inContent=n=>contentRegions.length?contentRegions.some(region=>region.contains(n)):!!document.querySelector('h1');
  const labeled=[];
  for(const n of [...document.querySelectorAll('li')].slice(0,1200)){
    if(!inContent(n)||ignored(n)||!hitPoint(n))continue;
    const text=visibleText(n);
    if(text.length<=180&&/^[^：:]{1,16}[：:]\s*\S/.test(text)&&
      /^(?:总?笔画|總?筆畫|部首|简化字|簡化字|异体字|異體字|读音|讀音|拼音|注音|词性|詞性|释义|釋義|字形|编码|編碼|Unicode|参数|參數|单位|單位)/i.test(text)){
      labeled.push({selector:selectorFor(n),text,bbox:round(n.getBoundingClientRect())});
    }
  }
  if(labeled.length>=3)Object.assign(reference,{found:true,kind:'labeled_reference_fields',reason:'At least3 actual exposed reference labels have explicit values.',evidence:labeled.slice(0,6)});
  if(!reference.found)for(const list of document.querySelectorAll('dl')){
    if(!inContent(list)||ignored(list))continue;
    const pairs=[];
    for(const term of list.querySelectorAll(':scope > dt')){
      const definition=term.nextElementSibling;
      if(!definition||definition.localName!=='dd'||!hitPoint(term)||!hitPoint(definition))continue;
      const label=visibleText(term),value=visibleText(definition);
      if(label&&label.length<=40&&value)pairs.push({label,value:value.slice(0,120),selector:selectorFor(term)});
    }
    if(pairs.length>=3){Object.assign(reference,{found:true,kind:'definition_list',reason:'At least3 exposed semantic dt/dd reference pairs.',evidence:pairs.slice(0,6)});break;}
  }
  if(!reference.found)for(const table of document.querySelectorAll('table')){
    if(!inContent(table)||ignored(table)||!hitPoint(table))continue;
    const rows=[...table.querySelectorAll('tr')].filter(row=>hitPoint(row));
    const cells=[...table.querySelectorAll('th,td')].filter(cell=>hitPoint(cell))
      .map(cell=>({node:cell,text:visibleText(cell)})).filter(row=>row.text);
    const headers=cells.filter(cell=>cell.node.localName==='th');
    if(rows.length>=2&&cells.length>=4&&headers.length>=1&&cells.reduce((n,c)=>n+c.text.length,0)>=20){
      Object.assign(reference,{found:true,kind:'reference_table',reason:'An actual visible multi-row table has exposed header and data cells.',
        evidence:cells.slice(0,8).map(c=>({text:c.text.slice(0,100),selector:selectorFor(c.node),is_header:c.node.localName==='th'}))});break;
    }
  }
  const paragraphs=[];
  const primaryHeading=[...document.querySelectorAll('article h1,main h1,[role="main"] h1,h1')]
    .find(n=>!ignored(n)&&styleVisible(n)&&clean(n.textContent).length>=4)||null;
  const primaryColumn=primaryHeading?.getBoundingClientRect();
  const primaryRegion=primaryHeading?.closest('article,[itemprop="articleBody"],[role="main"],main');
  const candidates=[...document.querySelectorAll('p,article > div,main > div,[itemprop="articleBody"] > div')];
  for(const p of candidates.slice(0,2000)){
    if(ignored(p)||!styleVisible(p))continue;
    const text=clean(p.textContent);
    const han=(text.match(/[\u3400-\u9fff]/g)||[]).length;
    const punctuation=(text.match(/[。！？；，、,.!?;]/g)||[]).length;
    const linked=[...p.querySelectorAll('a')].reduce((n,a)=>n+clean(a.textContent).length,0);
    if(text.length<65||han<35||punctuation<2||linked/Math.max(1,text.length)>.32||
      /^(?:广告推广|推广信息|广告位|赞助推广|advertisement|sponsored)/i.test(text))continue;
    // A wrapper containing several real paragraphs is not a separate paragraph.
    if(p.localName==='div'&&p.querySelector('p'))continue;
    // Settings/form panels concatenate labels and help text into long strings.
    // Several actual controls without a paragraph do not make that wrapper
    // prose, even when the page uses no aside/navigation landmark or long h1.
    if(p.localName==='div'&&p.querySelectorAll('input:not([type="hidden"]),textarea,select,button,[role="radio"],[role="checkbox"],[role="switch"],[role="button"]').length>=2)continue;
    const parent=p.closest('article,[itemprop="articleBody"],[role="main"],main')||p.parentElement;
    const r=p.getBoundingClientRect();
    if(primaryRegion&&!primaryRegion.contains(p))continue;
    if(primaryColumn&&primaryColumn.width>0){
      const overlap=Math.max(0,Math.min(primaryColumn.right,r.right)-Math.max(primaryColumn.left,r.left));
      // A long recommendation/sidebar paragraph is not the article's prose.
      // Associate with the actual primary heading's horizontal content column,
      // never with an expected title string or a domain-specific class name.
      if(overlap/Math.max(1,Math.min(r.width,primaryColumn.width))<.8||r.width<primaryColumn.width*.35)continue;
    }
    const evidence=intersect(r)?textEvidence(p):{text:'',complete_visible_lines:0,line_texts:[]};
    const visibleChars=evidence.text.replace(/\s/g,'').length;
    const fullParagraph=r.top>=0&&r.left>=0&&r.right<=width&&r.bottom<=height&&
      evidence.text.replace(/\s/g,'')===text.replace(/\s/g,'');
    const longBlock=r.height>height*.8&&text.length>=256&&visibleChars>=80&&evidence.complete_visible_lines>=2;
    paragraphs.push({node:p,parent,text,rect:r,score:Math.min(1200,text.length)+(p.closest('article,[itemprop="articleBody"]')?300:0),
      visible_text:evidence.text,text_evidence:evidence,full_paragraph:fullParagraph,long_block_readable:longBlock,
      readable:visibleChars>=50&&(fullParagraph||longBlock)});
  }
  paragraphs.sort((a,b)=>b.score-a.score);
  const best=paragraphs[0]||null;
  let body={found:!!best,visible:false,heading:'',excerpt:'',bbox:null,selector:null,
    reason:best?'A long, low-link prose paragraph exists in DOM.':'No sufficiently long, low-link prose paragraph found.',
    paragraph_count:paragraphs.length,visible_character_count:0};
  if(best){
    // Prefer an exposed paragraph over a longer offscreen one from same article.
    const exposed=paragraphs.find(p=>p.readable);
    const chosen=exposed||best;
    const heading=chosen.parent?.querySelector('h1,h2,[role="heading"]')||document.querySelector('h1');
    body={...body,visible:!!exposed,heading:heading?visibleText(heading):'',dom_heading:heading?clean(heading.textContent):'',
      excerpt:chosen.visible_text.slice(0,320),bbox:round(chosen.rect),selector:selectorFor(chosen.node),
      visible_character_count:chosen.visible_text.replace(/\s/g,'').length,
      reason:exposed?(chosen.full_paragraph?'A complete prose paragraph is inside viewport and every actual text range is exposed.':
        'Long-block policy: block is taller than80% viewport, >=256 source characters, >=80 exposed characters and >=2 completely exposed text lines; partial explicitly declared.'):
        'Prose exists but no complete exposed paragraph or qualifying long-block excerpt is readable.',
      document_top:Math.round(chosen.rect.top+scrollY),link_density_maximum:.32};
    body.full_paragraph_visible=chosen.full_paragraph;
    body.partial=chosen.visible_text.replace(/\s/g,'').length>0&&!chosen.full_paragraph;
    body.long_block_policy_applied=!!exposed&&chosen.long_block_readable&&!chosen.full_paragraph;
    body.complete_visible_lines=chosen.text_evidence.complete_visible_lines;
    body.complete_line_evidence=chosen.text_evidence.line_texts;
  }
  let obstruction={present:false,kind:'none',reason:'No dominant fixed/dialog obstruction detected.',close:null};
  const overlays=[];
  for(const n of [...document.querySelectorAll('body *')].slice(0,12000)){
    const s=getComputedStyle(n),r=n.getBoundingClientRect();
    const semantic=n.matches('dialog[open],[role="dialog"],[aria-modal="true"]');
    if(!semantic&&!['fixed','absolute'].includes(s.position))continue;
    if(intersect(r)<viewportArea*.09||r.width<120||r.height<60||!styleVisible(n))continue;
    const identity=clean((n.id||'')+' '+(typeof n.className==='string'?n.className:''));
    const z=Number(s.zIndex)||0;
    const atCenter=r.left<width*.65&&r.right>width*.35&&r.top<height*.65&&r.bottom>height*.35;
    const text=clean(n.textContent).slice(0,1600);
    const adEvidence=adWords.test(text)||/(?:^|[-_\s])(?:ad|ads|advert|popup|modal|dxlogin)(?:$|[-_\s])/i.test(identity);
    if(!semantic&&(!atCenter||!adEvidence||z<2))continue;
    const point=hitPoint(n);if(!point)continue;
    // Only report a painted overlay when it actually wins a point over content,
    // and prefer the innermost visible popup over a full-screen backdrop.
    const actualHit=document.elementFromPoint(...point);
    if(!actualHit||!n.contains(actualHit))continue;
    overlays.push({node:n,rect:r,semantic,adEvidence,text,area:intersect(r),score:(semantic?5:0)+(adEvidence?3:0)+(s.position==='fixed'?2:0)});
  }
  overlays.sort((a,b)=>b.score-a.score||a.area-b.area);
  const overlay=overlays[0];
  if(overlay){
    const n=overlay.node;let close=null,rejected=[];
    const hintCandidates=[];
    for(const hint of settings.close_hints||[]){
      let control=null;try{control=document.querySelectorAll(hint.selector)[hint.index||0];}catch(_){}
      if(!control||!n.contains(control)||!hitPoint(control)){
        rejected.push({selector:hint.selector,reason:'Bound hint is not an exposed descendant of this actual overlay.'});continue;
      }
      hintCandidates.push({control,hint});
    }
    const ordinary=[...n.querySelectorAll('button,[role="button"],a,input[type="button"],img,[onclick],.close,.close-btn,[aria-label]')]
      .map(control=>({control,hint:null}));
    for(const {control,hint} of [...hintCandidates,...ordinary]){
      const label=clean(control.getAttribute('aria-label')||control.getAttribute('title')||control.getAttribute('alt')||control.value||control.textContent);
      const identity=clean((control.id||'')+' '+(typeof control.className==='string'?control.className:''));
      const explicitLabel=safeClose.test(label);
      const explicitIdentity=/(?:^|[-_\s])(?:close|dismiss)(?:$|[-_\s])/i.test(identity);
      if(!explicitLabel&&!explicitIdentity&&!hint)continue;
      const point=hitPoint(control);if(!point)continue;
      const anchor=control.closest('a[href]'),form=control.closest('form');
      let unsafe=forbiddenAction.test(label);
      for(let owner=control;owner&&n.contains(owner);owner=owner.parentElement){
        const declaredHandler=owner.getAttribute('onclick')||'';
        if(/(?:window\s*\.\s*open|(?:window\s*\.\s*)?location|\.submit\s*\(|fetch\s*\()/i.test(declaredHandler))unsafe=true;
        if(owner===n)break;
      }
      if(anchor){
        const href=anchor.getAttribute('href')||'';
        if(href&&!href.startsWith('#')&&!/^javascript:\s*(?:void\(0\)|;?)\s*;?$/i.test(href))unsafe=true;
        if(anchor.target==='_blank'||anchor.hasAttribute('download'))unsafe=true;
      }
      if(control.localName==='button'&&(control.type==='submit'||!control.hasAttribute('type'))&&form)unsafe=true;
      if(unsafe){rejected.push({label,reason:'Navigation, submit, login/consent/purchase/download is not a safe close.'});continue;}
      close={selector:selectorFor(control),expected_text:label,dom_tag:control.localName,observed_bbox:round(control.getBoundingClientRect()),
        observed_hit_point:point,hint_evidence:hint?hint.evidence:null,
        reason:hint?'Hash-bound reviewed close hint, revalidated as exposed safe control inside current overlay.':
          'Observed exposed close label/identity inside actual overlay; no declared external navigation or form submission.'};break;
    }
    obstruction={present:true,kind:overlay.adEvidence?'advertising_overlay':'dialog_overlay',
      reason:'A visible fixed/dialog layer overlaps the central viewport; body visibility cannot imply readiness through it.',
      bbox:round(overlay.rect),selector:selectorFor(n),visible_text:visibleText(n).slice(0,320),close,
      rejected_close_candidates:rejected};
  }
  const links=[...document.querySelectorAll('a')].filter(n=>hitPoint(n)&&!ignored(n));
  const pageKind=actualForm?'tool':reference.found?'listing':best?'article':links.length>=5?'listing':'unknown';
  let decision;
  if(settings.mode==='off')decision={action:'not_applicable',reason:'Preparation explicitly disabled; observation retained.'};
  else if(operation.action_type==='complete')decision={action:'not_applicable',reason:'Planned completion never inserts another preparation action; collector must verify actual terminal assertions.'};
  else if(obstruction.present)decision=obstruction.close?
    {action:'close_overlay',selector:obstruction.close.selector,reason:'Use only observed safe close control, then reassess actual page.'}:
    {action:'blocked',reason:'Dominant overlay has no observed safe close; do not guess, click ads, or remove DOM.'};
  else if(operation.preserve_reading_position===true)decision={action:'not_applicable',reason:'This actual page was already prepared; preserve subsequent planned reading position instead of chasing earlier prose.'};
  else if(plannedPoint&&settings.mode!=='article')decision={action:'not_applicable',reason:'The next planned target is already exposed; preserve its navigation/control instead of scrolling it away.'};
  else if(actualForm&&settings.mode!=='article')decision={action:'not_applicable',reason:'Visible functional form/tool controls; prose scrolling is unnecessary.'};
  else if(reference.found&&settings.mode!=='article')decision={action:'not_applicable',reason:'Exposed structured reference fields/table are the current content; preserve them without forcing prose scrolling.'};
  else if(body.visible)decision={action:'ready',reason:'Actual prose is readable in current viewport.'};
  else if(best){
    const below=best.rect.top>=height*.65;
    if(below)decision={action:'scroll_to_content',distance:Math.min(settings.scroll_step_pixels||240,480,Math.max(1,Math.round(best.rect.top-height*.25))),direction:'down',
      reason:'Prose is below viewport; one bounded explicit scroll, then reassess, never jump or hide first screen.'};
    else if(best.rect.bottom<=0)decision={action:'blocked',reason:'Detected prose lies above viewport; no blind downward scroll.'};
    else decision={action:'blocked',reason:'Prose exists but actual readable text remains insufficient or occluded.'};
  } else if(pageKind==='listing'&&settings.mode!=='article')decision={action:'not_applicable',reason:'Navigation/listing page without validated prose; preserve planned navigation.'};
  else decision={action:'blocked',reason:'No verified prose or functional navigation target; no blind scrolling based on expected result.'};
  return {schema_version:'content-preparation-assessment-1',page_url:location.href,viewport:{width,height,scroll_x:scrollX,scroll_y:scrollY},
    page_kind:pageKind,body,obstruction,reference_content:reference,decision,next_target:{selector:operation.selector||null,visible_hit:!!plannedPoint,
      preserve_reading_position:operation.preserve_reading_position===true},
    observations_are_not_visual_QC:true,DOM_was_not_modified:true};
}
