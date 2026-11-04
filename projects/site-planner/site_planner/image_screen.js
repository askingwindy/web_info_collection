() => {
  const width=innerWidth,height=innerHeight;
  const visible=e=>{
    const r=e.getBoundingClientRect();if(r.width<=0||r.height<=0)return false;
    // display:contents / zero-height layout parents may still have visible children.
    for(let n=e;n;n=n.parentElement){const s=getComputedStyle(n);if(s.visibility!=='visible'||s.display==='none'||Number(s.opacity)<=0)return false;}
    return true;
  };
  const onScreen=e=>{const r=e.getBoundingClientRect();return visible(e)&&r.right>0&&r.bottom>0&&r.left<width&&r.top<height;};
  const elements=[];
  for(const img of document.images){
    if(!img.complete||img.naturalWidth<=0||!onScreen(img))continue;
    const r=img.getBoundingClientRect(),l=Math.max(0,r.left),t=Math.max(0,r.top),rr=Math.min(width,r.right),bb=Math.min(height,r.bottom);
    // Conservative exposure: a covering overlay is not image evidence.
    const exposed=[.15,.5,.85].every(x=>[.15,.5,.85].every(y=>document.elementFromPoint(l+(rr-l)*x,t+(bb-t)*y)===img));
    if(!exposed)continue;
    elements.push({element_type:'image',visible:true,bbox:[r.left,r.top,r.right,r.bottom]});
  }
  return {schema_version:'producer-image-viewport-observation-2',url:location.href,
    screen_resolution:[width,height],elements,inventory_complete:true};
}
