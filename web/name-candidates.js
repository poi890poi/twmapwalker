'use strict';
const MapwalkerNameCandidates=(()=>{
  function items(result){
    const seen=new Set(),out=[];
    function add(name,source,modern=false,annotated=false,metadata={}){
      name=String(name||'').normalize('NFKC').trim();
      const key=JSON.stringify([name,metadata.identity||'reading']);
      if(!name||name.length>80||seen.has(key))return;
      seen.add(key);out.push({name,source,modern,annotated,...metadata});
    }
    for(const nearby of (result.nearby_annotations||[]).slice(0,5)){
      const year=nearby.source==='JM50K_1916'?'1916':'1924';
      const geometry=nearby.relation==='overlapping label boxes'?'overlapping boxes':`~${nearby.distance_m} m between boxes`;
      add(nearby.name,`Saved POI #${nearby.poi_id} · ${year}${nearby.same_map?' · same map':' · other map'} · ${geometry}`,false,true,
        {identity:`saved/${nearby.poi_id}`,classification:nearby.classification||'poi',
          osm:nearby.osm_type&&nearby.osm_id?{type:nearby.osm_type,id:nearby.osm_id,name:nearby.osm_name||''}:null});
    }
    for(const name of (result.raw_readings||[]).slice(0,4))add(name,'Automatic map reading');
    let modernCount=0;
    for(const candidate of result.candidates||[]){
      if(modernCount>=8)break;
      const p=candidate.feature.properties,provider=p.provider==='moi'?'MOI place names':'OSM';
      const osm=p.provider!=='moi'&&p.osm_type&&p.osm_id?{type:p.osm_type,id:p.osm_id,name:p.name||''}:null;
      const identity=osm?`osm/${osm.type}/${osm.id}`:`moi/${p.record_id||p.name}`;
      const metadata={identity,classification:'poi',osm};
      const suffix=`${provider}${osm?' '+osm.type+' '+osm.id:''} · ~${candidate.distance_m} m · ${candidate.name_match?'name overlap':'nearby reference'}`;
      const previous=out.length;
      if(candidate.name_match)add(candidate.name_match.alias,suffix,true,false,metadata);
      add(p.name,suffix,true,false,metadata);
      for(const alias of (p.aliases||[]).slice(0,2))add(alias,`${suffix} · alternate name`,true,false,metadata);
      for(const [key,value] of Object.entries(p.tags||{})){
        if(key.split(':')[0]==='old_name')for(const alias of String(value).split(';'))add(alias,`${suffix} · old name`,true,false,metadata);
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
  draft.nameEvidence=result;
  const status=$('candidate-name-status');host.replaceChildren();
  const items=MapwalkerNameCandidates.items({...result,nearby_annotations:draft.nearbyNames||[]});
  status.textContent=items.length?'Select a POI to fill its name, type and OSM link, then save. Automatic readings fill only the label.':'No name suggestions yet. You can type a reading or use ? for unknown characters.';
  for(const item of items){
    const button=document.createElement('button');button.type='button';button.className='name-suggestion';
    const name=document.createElement('bdi');name.textContent=item.name;
    const source=document.createElement('small');source.textContent=item.source;
    button.append(name,source);
    button.onclick=()=>{
      if(annotationDraft!==draft)return;
      selectAnnotationSuggestion(item,draft);
      status.textContent=item.classification
        ?`Name and type filled; ${item.osm?'OSM link selected':'no OSM link for this POI'}. Save annotation to apply. ${item.annotated?'Check that it belongs to this label; proximity alone is not a match.':'Compare with the historical map before saving.'}`
        :'Automatic reading filled as a draft. Check the complete label before saving.';
    };
    host.append(button);
  }
}
async function loadNearbyAnnotatedNames(p){
  const draft=annotationDraft;if(!draft||draft.p.id!==p.id)return;
  try{
    const result=await api(`/api/pois/${p.id}/nearby-annotations`);
    if(annotationDraft!==draft)return;
    draft.nearbyNames=result.candidates;
    renderNameCandidates(p,draft.nameEvidence||{raw_readings:[p.text],candidates:[]});
  }catch(error){
    if(annotationDraft!==draft)return;
    const status=$('nearby-name-status');if(status)status.textContent='Nearby saved names unavailable. Other suggestions can still be used.';
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
