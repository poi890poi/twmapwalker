/* Mobile inspector size is presentation state: hiding never discards a draft. */
(function(root){
  'use strict';
  const states=['hidden','half','full'];
  function step(state,direction){return states[Math.max(0,Math.min(2,states.indexOf(state)+direction))];}
  function snap(state,dy,dx,height){
    if(Math.abs(dy)<32||Math.abs(dy)<=Math.abs(dx))return state;
    // A long drag may cross both stops; short swipes move one stop.
    if(Math.abs(dy)>height*.60)return dy<0?'full':'hidden';
    return step(state,dy<0?1:-1);
  }
  function attach({panel,handle,container,onResize,media}){
    let state='half',drag=null,suppressClick=false;
    const sizes={hidden:'44px',half:'50%',full:'100%'};
    function set(next){
      state=next;panel.dataset.sheetState=state;
      container.style.setProperty('--poi-sheet-height',sizes[state]);
      handle.setAttribute('aria-expanded',String(state!=='hidden'));
      handle.setAttribute('aria-label',`POI panel: ${state}. Swipe up to expand or down to hide. Arrow keys also resize.`);
      handle.querySelector('span').textContent=state==='hidden'?'Show POI':state==='full'?'Full height · swipe down for map':'Half height · swipe up or down';
      if(state==='hidden'&&panel.contains(panel.ownerDocument.activeElement))handle.focus({preventScroll:true});
      onResize();
    }
    function cancel(){drag=null;panel.classList.remove('sheet-dragging');set(state);}
    handle.addEventListener('pointerdown',event=>{
      if(!media.matches||!panel.open||event.isPrimary===false||event.button!==0)return;
      suppressClick=false;
      drag={id:event.pointerId,x:event.clientX,y:event.clientY,height:panel.getBoundingClientRect().height,
            total:container.getBoundingClientRect().height};
      handle.setPointerCapture(event.pointerId);
    });
    handle.addEventListener('pointermove',event=>{
      if(!drag||event.pointerId!==drag.id)return;
      const dy=event.clientY-drag.y,dx=event.clientX-drag.x;
      if(Math.max(Math.abs(dy),Math.abs(dx))>=8)suppressClick=true;
      if(Math.abs(dy)<8||Math.abs(dy)<=Math.abs(dx))return;
      suppressClick=true;panel.classList.add('sheet-dragging');
      container.style.setProperty('--poi-sheet-height',`${Math.max(44,Math.min(drag.total,drag.height-dy))}px`);
    });
    handle.addEventListener('pointerup',event=>{
      if(!drag||event.pointerId!==drag.id)return;
      const next=snap(state,event.clientY-drag.y,event.clientX-drag.x,drag.total);
      drag=null;panel.classList.remove('sheet-dragging');
      if(handle.hasPointerCapture(event.pointerId))handle.releasePointerCapture(event.pointerId);
      set(next);
    });
    handle.addEventListener('pointercancel',cancel);
    handle.addEventListener('lostpointercapture',()=>{if(drag)cancel();});
    handle.addEventListener('click',event=>{
      if(!media.matches)return;
      if(suppressClick&&event.detail!==0){suppressClick=false;return;}
      set(state==='full'?'half':state==='half'?'full':'half');
    });
    handle.addEventListener('keydown',event=>{
      if(!media.matches||!['ArrowUp','ArrowDown','Home','End'].includes(event.key))return;
      event.preventDefault();set(event.key==='Home'?'full':event.key==='End'?'hidden':step(state,event.key==='ArrowUp'?1:-1));
    });
    media.addEventListener('change',cancel);
    set(state);
    return {set,reveal(){if(media.matches&&state==='hidden')set('half');},get state(){return state;}};
  }
  const api={step,snap,attach};
  if(typeof module!=='undefined')module.exports=api;else root.MapwalkerSheet=api;
})(typeof window!=='undefined'?window:globalThis);
