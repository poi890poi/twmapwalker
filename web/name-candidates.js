'use strict';
const MapwalkerNameCandidates=(()=>{
  function items(result){
    const seen=new Set(),out=[];
    function add(name,source,modern=false){
      name=String(name||'').normalize('NFKC').trim();
      if(!name||name.length>80||seen.has(name))return;
      seen.add(name);out.push({name,source,modern});
    }
    for(const name of (result.raw_readings||[]).slice(0,4))add(name,'Automatic map reading');
    let modernCount=0;
    for(const candidate of result.candidates||[]){
      if(modernCount>=8)break;
      const p=candidate.feature.properties,provider=p.provider==='moi'?'MOI place names':'OSM';
      const suffix=`${provider} · ~${candidate.distance_m} m · ${candidate.name_match?'name overlap':'nearby reference'}`;
      const previous=out.length;
      if(candidate.name_match)add(candidate.name_match.alias,suffix,true);
      add(p.name,suffix,true);
      for(const alias of (p.aliases||[]).slice(0,2))add(alias,`${provider} alternate name · ~${candidate.distance_m} m`,true);
      for(const [key,value] of Object.entries(p.tags||{})){
        if(key.split(':')[0]==='old_name')for(const alias of String(value).split(';'))add(alias,`${provider} old name · ~${candidate.distance_m} m`,true);
      }
      modernCount+=out.length-previous;
    }
    return out.slice(0,12);
  }
  function apply(input,name){
    // Use the same input event path as typing: dirty tracking, direction preview
    // and OSM suggestions update without touching any other annotation field.
    input.value=name;input.dispatchEvent(new Event('input',{bubbles:true}));input.focus();
  }
  return {items,apply};
})();
function renderNameCandidates(p,result){
  const draft=annotationDraft,host=$('candidate-names');
  if(!host||!draft||draft.p.id!==p.id)return;
  const status=$('candidate-name-status');host.replaceChildren();
  const items=MapwalkerNameCandidates.items(result);
  status.textContent=items.length?'Tap to fill the label, then edit and save. Modern names may differ from the map.':'No name suggestions yet. You can type a reading or use ? for unknown characters.';
  for(const item of items){
    const button=document.createElement('button');button.type='button';button.className='name-suggestion';
    const name=document.createElement('bdi');name.textContent=item.name;
    const source=document.createElement('small');source.textContent=item.source;
    button.append(name,source);
    button.onclick=()=>{
      if(annotationDraft!==draft)return;
      const input=$('annotation-name');MapwalkerNameCandidates.apply(input,item.name);
      status.textContent=item.modern?'Modern name filled as a draft. Compare with the historical map before saving.':'Automatic reading filled as a draft. Check the complete label before saving.';
    };
    host.append(button);
  }
}
function bindReadingSuggestions(p){
  const draft=annotationDraft,host=$('reread-results'),status=$('reread-status');
  const buttons=['numbers','kana'].map(mode=>$('reread-'+mode));
  for(const [index,mode] of ['numbers','kana'].entries()){
    const button=buttons[index];button.disabled=p.kind==='trail';
    button.onclick=async()=>{
      if(annotationDraft!==draft)return;
      for(const b of buttons)b.disabled=true;
      status.textContent='Reading the original map pixels…';host.replaceChildren();
      try{
        const result=await api(`/api/pois/${p.id}/reading-suggestions?mode=${mode}`);
        if(annotationDraft!==draft||$('reread-results')!==host)return;
        status.textContent=result.readings.length
          ?mode==='numbers'?'Tap a draft reading. Check missing digits and decimal marks; a number alone cannot distinguish a peak from a contour.':'Tap a draft reading. This may be only one piece of the complete name.'
          :'No usable reading found. Try selecting label pieces or type what you can read.';
        for(const reading of result.readings){
          const choice=document.createElement('button');choice.type='button';choice.className='name-suggestion';
          const text=document.createElement('bdi');text.textContent=reading.text;
          const source=document.createElement('small');source.textContent=`${mode==='numbers'?'Expanded map crop':'Japanese reader'} · ${reading.angle}° · unverified`;
          choice.append(text,source);choice.onclick=()=>{
            if(annotationDraft===draft)MapwalkerNameCandidates.apply($('annotation-name'),reading.text);
          };host.append(choice);
        }
      }catch(error){if(annotationDraft===draft)status.textContent='Reading unavailable: '+error.message;}
      finally{if(annotationDraft===draft)for(const b of buttons)b.disabled=false;}
    };
  }
}
if(typeof module!=='undefined')module.exports=MapwalkerNameCandidates;
