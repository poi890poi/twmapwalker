'use strict';
let previewAttributed=false,annotationDraft=null,fragmentRequest=0,osmSuggestTimer,osmSuggestSequence=0,directionTimer,directionSequence=0;
const fragmentLayer=L.layerGroup(),osmPreview=L.layerGroup();
function fragmentRecord(p){return {...p,box:typeof p.box==='string'?JSON.parse(p.box):p.box};}
function annotationHistory(rows){return rows.length?rows.slice().reverse().map(r=>`<li><bdi>${escapeHTML(r.payload.ground_truth||'(no name)')}</bdi> · ${escapeHTML(r.payload.classification||'unclassified')}<br>${escapeHTML(r.payload.note||'')}</li>`).join(''):'<li>No saved annotations.</li>';}
function annotationEditor(p){
  const a=p.annotation||{},text=a.ground_truth??p.reading??p.text??'';
  return `<section class="annotation-editor">
    <label class="full-label" for="annotation-name">Full label on the map</label>
    <p class="annotation-help" id="label-help">Include characters the detector missed. Type in reading order; use <strong>?</strong> for unreadable characters.</p>
    <input id="annotation-name" dir="auto" maxlength="80" aria-describedby="label-help" value="${escapeHTML(text)}" placeholder="e.g. ウライ社 or ?ライ社" autocomplete="off">
    <p id="direction-status" role="status" aria-live="polite">Checking writing direction…</p>
    <fieldset class="annotation-choice"><legend>What is this?</legend><button type="button" data-class="poi">POI</button><button type="button" data-class="unclassified">Not sure</button><button type="button" data-class="noise">Noise</button></fieldset>
    <input id="annotation-class" type="hidden" value="${escapeHTML(a.classification||'unclassified')}"><input id="annotation-members" type="hidden"><input id="annotation-osm" type="hidden">
    <div class="fragment-heading"><h3>Parts of this label</h3><button id="pick-fragments" aria-pressed="false">＋ Select on map</button></div>
    <p id="fragment-help">Combine pieces that belong to the same label. Saving applies the annotation to every selected piece.</p><div id="fragment-members" class="fragment-members"></div>
    <details id="osm-matches" class="evidence-section" ${a.osm_type?'open':''}><summary>Match an OpenStreetMap object <span id="osm-link-badge">${a.osm_type?'· linked':''}</span></summary>
      <div id="osm-selected"></div><p id="osm-suggestion-status" role="status">Open to find nearby matches.</p><div id="osm-suggestions"></div>
      <button id="retry-osm" hidden>Retry matches</button>
      <details class="osm-manual"><summary>Paste an OSM link instead</summary><label for="osm-url">OpenStreetMap object link</label><div class="osm-url-row"><input id="osm-url" type="url" placeholder="https://www.openstreetmap.org/node/…"><button id="use-osm-url">Use link</button></div><p id="osm-url-error" role="status"></p></details>
    </details>
    <details class="evidence-section"><summary>Direction, notes & history</summary>
      <label for="annotation-direction">Writing direction on the original map</label><select id="annotation-direction"><option value="auto">Automatic · compare matching glyphs</option><option value="unknown">Leave unknown</option><option value="ltr">Left to right</option><option value="rtl">Right to left</option><option value="vertical">Vertical</option></select>
      <p>For historical right-to-left Chinese/Japanese, type the correctly read name above. Arabic/Hebrew display direction is automatic.</p>
      <label for="annotation-note">Notes</label><textarea id="annotation-note" dir="auto" maxlength="2000" rows="2">${escapeHTML(a.note||'')}</textarea>
      <details><summary>Annotation history</summary><ul id="annotation-history">${annotationHistory(p.annotations||[])}</ul></details>
    </details>
    </section>`;
}
function annotationCleanup(){
  clearTimeout(directionTimer);directionSequence++;
  clearTimeout(osmSuggestTimer);osmSuggestSequence++;fragmentRequest++;map.removeLayer(fragmentLayer);fragmentLayer.clearLayers();osmPreview.clearLayers();map.removeLayer(osmPreview);
  if(!map.hasLayer(markers))markers.addTo(map);
  if(previewAttributed){map.attributionControl.removeAttribution('© OpenStreetMap contributors');previewAttributed=false;}
  annotationDraft=null;document.body.classList.remove('picking-fragments');$('fragment-mode').hidden=true;
}
function drawAnnotationSelection(){
  if(!annotationDraft)return;
  selectedOutline.clearLayers();
  for(const item of annotationDraft.members.values()){
    const b=MapwalkerPOI.bounds(item);
    L.rectangle([[b[1],b[0]],[b[3],b[2]]],{color:'#e55b24',weight:3,fillOpacity:.06,interactive:false}).addTo(selectedOutline);
  }
}
function renderFragmentMembers(){
  const draft=annotationDraft;if(!draft)return;
  const host=$('fragment-members');host.replaceChildren();
  $('annotation-members').value=JSON.stringify([...draft.members.keys()].sort((a,b)=>a-b));
  for(const p of draft.members.values()){
    const card=document.createElement('div');card.className='fragment-member';
    card.innerHTML=`<img src="/api/pois/${p.id}/image?thumbnail=true" alt="Selected map fragment"><bdi>${escapeHTML(p.text||'Unread fragment')}</bdi>`;
    if(p.id!==draft.p.id){const remove=document.createElement('button');remove.textContent='×';remove.setAttribute('aria-label',`Remove fragment ${p.text||p.id}`);remove.onclick=()=>{draft.members.delete(p.id);renderFragmentMembers();};card.append(remove);}
    else {const note=document.createElement('small');note.textContent='Selected POI';card.append(note);}
    host.append(card);
  }
  drawAnnotationSelection();
  annotationChanged();
  scheduleDirection();
  renderVisibility();
}
function renderVisibility(){
  const draft=annotationDraft;if(!draft)return;
  const count=draft.members.size,hidden=draft.p.hidden;
  $('hide-poi').textContent=hidden?(count>1?'Restore pieces':'Restore POI'):(count>1?`Hide ${count} pieces`:'Hide for now');
  $('hide-poi').title=hidden?'Return selected pieces to the visible map and list':'Hide selected pieces without changing annotations or review status';
  $('visibility-status').hidden=!hidden;
  $('visibility-status').textContent=hidden?'Hidden for now. Find it under Show → Hidden for now.':'';
}
async function togglePOIVisibility(){
  const draft=annotationDraft;if(!draft)return;
  const button=$('hide-poi'),hidden=!draft.p.hidden;
  button.disabled=true;
  try{
    await post(`/api/pois/${draft.p.id}/visibility`,{hidden,member_ids:[...draft.members.keys()]});
    if(!isCurrentDetail(draft.p))return;
    draft.p.hidden=hidden;renderVisibility();refresh();
    toast(hidden?'Hidden for now. Annotations and review status are preserved.':'POI restored.');
  }catch(error){if(isCurrentDetail(draft.p)){$('visibility-status').hidden=false;$('visibility-status').textContent=error.message;}}
  finally{if(isCurrentDetail(draft.p))button.disabled=false;}
}
function annotationChanged(){if(detailSaved.has('annotation-editor'))$('annotation-status').textContent=detailIsDirty()?'Unsaved changes.':'Saved.';}
function showDirection(result){
  const names={ltr:'Left to right',rtl:'Right to left',vertical:'Vertical'};
  $('direction-status').textContent=result.direction==='unknown'
    ?result.reason==='conflicting-glyph-order'?'Direction unclear · glyph order conflicts. You can set it below.':'Direction unclear · needs two unambiguous matching glyphs.'
    :`${names[result.direction]} · inferred from ${result.matched_glyphs.length} matching glyphs (${result.matched_glyphs.join(' · ')}).`;
}
function scheduleDirection(){
  clearTimeout(directionTimer);const sequence=++directionSequence,draft=annotationDraft;
  if(!draft)return;
  const choice=$('annotation-direction');
  if(choice.value!=='auto'){$('direction-status').textContent='Writing direction: '+choice.selectedOptions[0].textContent+' · manual';return;}
  $('direction-status').textContent='Comparing glyph order with your label…';
  const label=$('annotation-name').value,member_ids=[...draft.members.keys()];
  directionTimer=setTimeout(async()=>{
    try{
      const result=await post(`/api/pois/${draft.p.id}/writing-direction`,{label,member_ids});
      if(sequence===directionSequence&&annotationDraft===draft)showDirection(result);
    }catch(error){if(sequence===directionSequence&&annotationDraft===draft)$('direction-status').textContent='Direction preview unavailable. You can set it below.';}
  },200);
}
async function pickAnnotationFragment(id){
  const draft=annotationDraft;if(!draft?.picking)return false;
  if(id===draft.p.id)return true;
  if(draft.members.has(id)){draft.members.delete(id);renderFragmentMembers();return true;}
  try{
    const p=await api(`/api/pois/${id}`);
    if(annotationDraft!==draft||!draft.picking)return true;
    if(p.source!==draft.p.source)throw Error('Select fragments from the same historical map.');
    const additions=p.group_members?.length?p.group_members:[p];
    if(new Set([...draft.members.keys(),...additions.map(p=>p.id)]).size>100)throw Error('A label can contain at most 100 fragments.');
    for(const member of additions)draft.members.set(member.id,fragmentRecord(member));
    renderFragmentMembers();$('fragment-help').textContent=`${draft.members.size} pieces selected. Remove a piece with ×; save when ready.`;
  }catch(error){if(annotationDraft===draft)$('fragment-help').textContent=error.message;}
  return true;
}
async function loadFragmentChoices(){
  const draft=annotationDraft;if(!draft?.picking||!bbox())return;
  const sequence=++fragmentRequest;
  try{
    const result=await api('/api/pois?'+new URLSearchParams({bbox:bbox().join(','),source:draft.p.source,display:'all',disposition:'all',include_trails:false,limit:300}));
    if(sequence!==fragmentRequest||annotationDraft!==draft||!draft.picking)return;
    fragmentLayer.clearLayers();
    for(const item of result.items){
      const p=fragmentRecord(item),b=MapwalkerPOI.bounds(p);
      L.rectangle([[b[1],b[0]],[b[3],b[2]]],{color:'#276f91',weight:2,fillOpacity:.12}).bindTooltip(escapeHTML(p.text||'Unread fragment')).on('click',()=>pickAnnotationFragment(p.id)).addTo(fragmentLayer);
      L.marker([p.lat,p.lon],{icon:L.divIcon({className:'fragment-pick-pin',html:'<span>＋</span>',iconSize:[28,28]}),title:'Select fragment: '+(p.text||p.id),keyboard:true}).on('click',()=>pickAnnotationFragment(p.id)).addTo(fragmentLayer);
    }
    drawAnnotationSelection();
    $('fragment-help').textContent=result.total>300?'Showing 300 candidates. Zoom in to select the remaining pieces.':'Tap blue boxes or + markers to add pieces. Tap again to remove.';
  }catch(error){if(annotationDraft===draft)$('fragment-help').textContent='Unable to load fragments. '+error.message;}
}
function setFragmentPicking(enabled){
  const draft=annotationDraft;if(!draft)return;draft.picking=enabled;
  $('pick-fragments').textContent=enabled?'Done selecting':'＋ Select on map';$('pick-fragments').setAttribute('aria-pressed',String(enabled));
  document.body.classList.toggle('picking-fragments',enabled);$('fragment-mode').hidden=!enabled;
  if(enabled){map.removeLayer(markers);fragmentLayer.addTo(map);loadFragmentChoices();}
  else{fragmentRequest++;map.removeLayer(fragmentLayer);markers.addTo(map);drawAnnotationSelection();}
}
map.on('moveend',()=>{if(annotationDraft?.picking)loadFragmentChoices();});
$('finish-fragments').onclick=()=>setFragmentPicking(false);
function renderOSMSelection(){
  const draft=annotationDraft,host=$('osm-selected');if(!draft||!host)return;
  $('annotation-osm').value=JSON.stringify(draft.osm);$('osm-link-badge').textContent=draft.osm?'· linked':'';host.replaceChildren();
  annotationChanged();
  if(!draft.osm)return;
  const a=draft.osm,link=document.createElement('a');link.href=`https://www.openstreetmap.org/${a.type}/${a.id}`;link.target='_blank';link.rel='noopener';link.textContent=a.name||`${a.type} ${a.id}`;
  const remove=document.createElement('button');remove.textContent='Unlink';remove.onclick=()=>{draft.osm=null;osmPreview.clearLayers();renderOSMSelection();};host.append(link,remove);
}
function previewOSM(feature){
  if(!previewAttributed){map.attributionControl.addAttribution('© OpenStreetMap contributors');previewAttributed=true;}
  osmPreview.clearLayers();L.geoJSON(feature,{style:{color:'#287cb0',weight:5},pointToLayer:(feature,point)=>L.circleMarker(point,{radius:9,color:'#287cb0',weight:3,fillOpacity:.2})}).addTo(osmPreview);osmPreview.addTo(map);
  const layer=L.geoJSON(feature),bounds=layer.getBounds();
  if(annotationDraft)for(const p of annotationDraft.members.values()){const b=MapwalkerPOI.bounds(p);bounds.extend([b[1],b[0]]);bounds.extend([b[3],b[2]]);}
  map.fitBounds(bounds,{padding:[60,60],maxZoom:17});
}
async function loadOSMSuggestions(){
  const draft=annotationDraft;if(!draft||!$('osm-matches')?.open)return;
  const sequence=++osmSuggestSequence,q=$('annotation-name').value;$('osm-suggestion-status').textContent='Finding name and geometry matches…';$('retry-osm').hidden=true;
  try{
    const result=await api(`/api/pois/${draft.p.id}/osm-suggestions?`+new URLSearchParams({q}));
    if(sequence!==osmSuggestSequence||annotationDraft!==draft)return;
    const host=$('osm-suggestions');host.replaceChildren();
    for(const feature of result.features){
      const p=feature.properties,card=document.createElement('div');card.className='osm-match';
      card.innerHTML=`<strong dir="auto">${escapeHTML(p.name||p.tags?.natural||p.tags?.waterway||p.category||'Unnamed object')}</strong><small>${escapeHTML(p.match_reason)} · ${p.distance_m} m to geometry${p.matched_name&&p.matched_name!==p.name?' · '+escapeHTML(p.matched_name):''}</small>`;
      const preview=document.createElement('button');preview.textContent='Show on map';preview.onclick=()=>previewOSM(feature);
      const use=document.createElement('button');use.textContent='Link this object';use.onclick=()=>{draft.osm={type:p.osm_type,id:p.osm_id,name:p.name||''};renderOSMSelection();previewOSM(feature);};
      card.append(preview,use);host.append(card);
    }
    const status=result.state==='pending'||result.state==='running'?'Loading OSM in the background…':result.state==='failed'?'OSM unavailable; showing cached matches if available.':result.features.length?`${result.text_used?'Name and geometry':'Geometry-only'} suggestions within 1 km. Historical identity needs your review.`:'No OSM candidates within 1 km. You can paste an object link below.';
    $('osm-suggestion-status').textContent=status+(result.truncated?' Nearby results were limited.':'');
    if(result.state==='pending'||result.state==='running')osmSuggestTimer=setTimeout(loadOSMSuggestions,5000);
    if(result.state==='failed')$('retry-osm').hidden=false;
  }catch(error){if(sequence===osmSuggestSequence&&annotationDraft===draft){$('osm-suggestion-status').textContent=error.message;$('retry-osm').hidden=false;}}
}
function bindAnnotationEditor(p){
  const a=p.annotation||{};
  annotationDraft={p,picking:false,members:new Map((p.group_members?.length?p.group_members:[p]).map(p=>[p.id,fragmentRecord(p)])),osm:a.osm_type?{type:a.osm_type,id:a.osm_id,name:a.osm_name||''}:null};
  $('hide-poi').disabled=false;$('hide-poi').onclick=togglePOIVisibility;
  $('annotation-direction').value=a.direction_source==='automatic'||!a.map_direction||(a.map_direction==='unknown'&&a.direction_source!=='manual')?'auto':a.map_direction;
  $('annotation-direction').onchange=scheduleDirection;
  const setClass=value=>{$('annotation-class').value=value;for(const button of document.querySelectorAll('[data-class]'))button.setAttribute('aria-pressed',String(button.dataset.class===value));annotationChanged();};
  for(const button of document.querySelectorAll('[data-class]'))button.onclick=()=>setClass(button.dataset.class);
  setClass(a.classification||({confirmed:'poi',rejected:'noise'}[p.reviews?.at(-1)?.verdict])||'unclassified');
  renderFragmentMembers();renderOSMSelection();
  $('pick-fragments').onclick=()=>setFragmentPicking(!annotationDraft.picking);
  $('osm-matches').ontoggle=()=>{if($('osm-matches').open)loadOSMSuggestions();else{clearTimeout(osmSuggestTimer);osmSuggestSequence++;}};
  $('retry-osm').onclick=loadOSMSuggestions;
  $('annotation-name').oninput=()=>{scheduleDirection();clearTimeout(osmSuggestTimer);osmSuggestSequence++;osmSuggestTimer=setTimeout(loadOSMSuggestions,350);};
  document.querySelector('.annotation-editor').oninput=annotationChanged;
  document.querySelector('.annotation-editor').onchange=annotationChanged;
  $('use-osm-url').onclick=()=>{
    try{const url=new URL($('osm-url').value),match=url.pathname.match(/^\/(node|way|relation)\/([1-9]\d*)\/?$/);
      if(!['https:','http:'].includes(url.protocol)||!['www.openstreetmap.org','openstreetmap.org'].includes(url.hostname)||!match||!Number.isSafeInteger(Number(match[2])))throw Error('Paste a node, way or relation link from openstreetmap.org.');
      annotationDraft.osm={type:match[1],id:Number(match[2]),name:''};$('osm-url').value='';$('osm-url-error').textContent='';renderOSMSelection();
    }catch(error){$('osm-url-error').textContent=error.message;}
  };
  $('save-annotation').onclick=async()=>{
    const draft=annotationDraft,button=$('save-annotation'),values=detailValues('annotation-editor');button.disabled=true;
    $('annotation-status').textContent='Saving…';
    try{
      const result=await post(`/api/pois/${p.id}/annotation`,{ground_truth:$('annotation-name').value,classification:$('annotation-class').value,map_direction:$('annotation-direction').value,member_ids:[...draft.members.keys()],sync_reading:true,osm_type:draft.osm?.type||'',osm_id:draft.osm?.id??null,osm_name:draft.osm?.name||'',note:$('annotation-note').value});
      if(!isCurrentDetail(p))return;
      p.annotation=result.annotation;(p.annotations||=[]).push({payload:result.annotation});p.group_members=[...draft.members.values()];p.reading=result.annotation.ground_truth;p.display_text=p.reading||p.text;
      const unchanged=detailValues('annotation-editor')===values;
      if(unchanged)$('annotation-name').value=result.annotation.ground_truth;
      if(unchanged&&result.annotation.direction_source==='automatic')showDirection(result.annotation.direction_evidence);
      markDetailSaved('annotation-editor',unchanged?detailValues('annotation-editor'):values);
      $('annotation-history').innerHTML=annotationHistory(p.annotations);$('detail-title').textContent=label(p);
      $('annotation-status').textContent=unchanged?'Saved.':'Saved earlier changes; newer edits are unsaved.';setFragmentPicking(false);refresh();
    }catch(error){if(isCurrentDetail(p))$('annotation-status').textContent=error.message;}
    finally{if(isCurrentDetail(p))button.disabled=false;}
  };
  if($('osm-matches').open)loadOSMSuggestions();
}
