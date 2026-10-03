'use strict';
function vegetationReviewState(request,changed){
  const state={data:null,selected:new Set(),after:0,history:[],busy:false,message:''};
  let sequence=0;
  async function load(after=state.after,history=state.history){
    if(state.busy)return;
    const token=++sequence;state.busy=true;changed(state);
    try{const data=await request(`/api/vegetation-review?after=${after}&limit=24`);
      if(token!==sequence)return;state.data=data;state.after=after;state.history=history;state.selected.clear();
    }catch(e){state.message=e.message;}finally{if(token===sequence){state.busy=false;changed(state);}}
  }
  async function decide(outcome){
    if(state.busy||!state.data||!state.selected.size)return;
    const items=state.data.items.filter(r=>state.selected.has(r.id)).map(r=>({id:r.id,input_key:r.input_key}));
    state.busy=true;changed(state);
    try{const result=await request('/api/vegetation-review/decisions',{profile:state.data.profile,items,outcome});
      state.message=outcome==='other'?`${result.saved} findings saved as Other. They are now hidden from normal browsing.`:`${result.saved} suggestions dismissed. Their findings are unchanged.`;
      state.selected.clear();state.busy=false;await load();
    }catch(e){state.message=e.message;state.busy=false;changed(state);}
  }
  function select(ids){if(state.busy||!state.data)return;state.selected=new Set(state.data.items.filter(r=>ids.includes(r.id)).map(r=>r.id));changed(state);}
  return {state,load,decide,select};
}
if(typeof module!=='undefined')module.exports={vegetationReviewState};
if(typeof document!=='undefined'){
  const $=id=>document.getElementById(id);
  const request=async(url,payload)=>{
    const response=await accessFetch(url,payload?{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(payload)}:{});
    const value=await response.json();if(!response.ok)throw Error(value.detail||'Review unavailable. Try again.');return value;
  };
  let rendered=null,renderedAfter=0;
  const review=vegetationReviewState(request,state=>{
    $('review-status').textContent=state.message;
    $('selected-count').textContent=`${state.selected.size} selected`;
    for(const id of ['refresh','select-page','clear-selection'])$(id).disabled=state.busy;
    $('accept').disabled=$('dismiss').disabled=state.busy||!state.selected.size;
    $('previous').disabled=state.busy||!state.history.length;
    $('next').disabled=state.busy||!state.data?.next_after;
    if(!state.data)return;
    const run=state.data.run,counts=state.data.checks;
    $('scan-status').textContent=run?`Scan ${run.state} · ${run.processed.toLocaleString()} checked / ${run.total.toLocaleString()} eligible at start · ${(counts['numeric-context']||0).toLocaleString()} numeric vetoes · ${(counts.error||0).toLocaleString()} unavailable. ${state.data.remaining} suggestions from this page onward.`:'No batch scan has been run yet.';
    if(rendered!==state.data){
      const pageChanged=rendered&&renderedAfter!==state.after;renderedAfter=state.after;
      rendered=state.data;$('review-cards').replaceChildren();
      for(const row of state.data.items){
        const card=document.createElement('article');card.className='card';
        const label=document.createElement('label'),box=document.createElement('input');box.type='checkbox';box.value=row.id;
        box.onchange=()=>{const ids=new Set(review.state.selected);box.checked?ids.add(row.id):ids.delete(row.id);review.select([...ids]);};
        label.append(box,document.createTextNode(`Select #${row.id}`));
        const image=document.createElement('img');image.src=row.preview;image.alt=`Original map and matching vegetation shape for proposal ${row.id}`;
        const caption=document.createElement('p');caption.textContent=`${row.source==='JM50K_1916'?'1916':'1924'} map · ${row.lat.toFixed(5)}° N, ${row.lon.toFixed(5)}° E`;
        const link=document.createElement('a');link.textContent='Inspect on map ↗';link.target='_blank';link.rel='noopener';
        link.href=`/?poi=${row.id}#lat=${row.lat}&lon=${row.lon}&z=19&source=${row.source}&display=all&visibility=all`;
        card.append(label,image,caption,link);$('review-cards').append(card);
      }
      if(!state.data.items.length)$('review-cards').textContent='No pending suggestions here. Refresh after the scan progresses, or return to the previous page.';
      if(pageChanged)$('review-cards').querySelector('input')?.focus();
    }
    for(const box of $('review-cards').querySelectorAll('input')){box.checked=state.selected.has(Number(box.value));box.disabled=state.busy;}
  });
  $('refresh').onclick=()=>review.load();
  $('select-page').onclick=()=>review.select(review.state.data?.items.map(r=>r.id)||[]);
  $('clear-selection').onclick=()=>review.select([]);
  $('accept').onclick=()=>review.decide('other');$('dismiss').onclick=()=>review.decide('dismiss');
  $('next').onclick=()=>{const state=review.state;if(state.busy||!state.data?.next_after)return;review.load(state.data.next_after,[...state.history,state.after]);};
  $('previous').onclick=()=>{const state=review.state;if(!state.busy&&state.history.length)review.load(state.history.at(-1),state.history.slice(0,-1));};
  review.load();
}
