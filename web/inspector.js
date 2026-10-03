'use strict';
const selectedOutline=L.layerGroup().addTo(map);
let detailPOI=null,detailSequence=0,detailTab='annotation',detailReturnFocus=null;
let detailPendingAction=null;
const detailSaved=new Map();
const detailSheet=MapwalkerSheet.attach({panel:$('detail'),handle:$('poi-sheet-handle'),container:document.querySelector('main'),
  media:window.matchMedia('(max-width:760px)'),onResize:()=>{if($('map').clientHeight>0)map.invalidateSize({pan:false});}});
function detailValues(section){
  return JSON.stringify([...document.querySelectorAll(`#detail .${section} input, #detail .${section} select, #detail .${section} textarea`)].map(el=>[el.id,el.type==='checkbox'?el.checked:el.value]));
}
function markDetailSaved(section,value=detailValues(section)){detailSaved.set(section,value);}
function detailIsDirty(){return [...detailSaved].some(([section,value])=>detailValues(section)!==value);}
function canLeaveDetail(action){
  if(!detailIsDirty())return true;
  detailSheet.reveal();
  detailPendingAction=action;$('detail-unsaved').hidden=false;$('keep-editing').focus();return false;
}
$('keep-editing').onclick=()=>{detailPendingAction=null;$('detail-unsaved').hidden=true;};
$('discard-edits').onclick=()=>{const action=detailPendingAction;detailPendingAction=null;detailSaved.clear();$('detail-unsaved').hidden=true;action?.();};
function isCurrentDetail(p){return detailPOI===p&&$('detail').open;}
function showDetailTab(tab,focus=false){
  detailTab=tab;
  $('annotation-footer').hidden=tab!=='annotation';
  if(tab!=='annotation'&&annotationDraft?.picking)setFragmentPicking(false);
  for(const name of ['evidence','annotation']){
    $(name+'-tab').setAttribute('aria-selected',String(name===tab));
    $(name+'-tab').tabIndex=name===tab?0:-1;
    if($(name+'-panel'))$(name+'-panel').hidden=name!==tab;
  }
  $('detail-body').scrollTop=0;
  if(focus)$(tab+'-tab').focus();
}
for(const name of ['evidence','annotation']){
  $(name+'-tab').onclick=()=>showDetailTab(name);
  $(name+'-tab').onkeydown=event=>{
    if(['ArrowLeft','ArrowRight','Home','End'].includes(event.key)){
      event.preventDefault();showDetailTab(event.key==='Home'?'evidence':event.key==='End'?'annotation':name==='evidence'?'annotation':'evidence',true);
    }
  };
}
function focusPOI(p){
  if($('map').clientHeight<1)return;
  document.body.classList.remove('map-tools-open');
  $('map-tools-toggle').textContent='Layers & places';$('map-tools-toggle').setAttribute('aria-expanded','false');
  map.invalidateSize({pan:false});
  const b=MapwalkerPOI.bounds(p),bounds=L.latLngBounds([[b[1],b[0]],[b[3],b[2]]]);
  if(annotationDraft?.p===p){
    for(const member of annotationDraft.members.values()){const b=MapwalkerPOI.bounds(member);bounds.extend([b[1],b[0]]);bounds.extend([b[3],b[2]]);}
    drawAnnotationSelection();
  }else{selectedOutline.clearLayers();L.rectangle(bounds,{color:'#e55b24',weight:3,fillOpacity:.06,interactive:false}).addTo(selectedOutline);}
  // Fit terrain around the finding; the orange outline still marks its exact box.
  const context=MapwalkerPOI.contextBounds([bounds.getWest(),bounds.getSouth(),bounds.getEast(),bounds.getNorth()]);
  const size=map.getSize();if(size.x<1||size.y<1)return;
  map.fitBounds([[context[1],context[0]],[context[3],context[2]]],{maxZoom:16,paddingTopLeft:[Math.min(65,size.x*.18),Math.min(70,size.y*.25)],paddingBottomRight:[Math.min(40,size.x*.12),Math.min(40,size.y*.15)],animate:false});
}
function closeDetail(showList=false){
  if(!$('detail').open)return true;
  if(!canLeaveDetail(()=>closeDetail(showList)))return false;
  annotationCleanup();detailSequence++;selectedId=null;detailPOI=null;detailSaved.clear();selectedOutline.clearLayers();$('detail-unsaved').hidden=true;
  $('detail').close();document.body.classList.remove('detail-open');
  detailSheet.set('half');
  document.body.classList.toggle('show-list',showList);
  $('toggle-list').textContent=showList?'Show map':'POI list';$('toggle-list').setAttribute('aria-expanded',String(showList));
  map.invalidateSize({pan:false});
  if(showList){const card=document.querySelector(`[data-poi-id="${detailReturnFocus}"]`);(card||$('name-search')).focus({preventScroll:true});}
  saveView();return true;
}
$('close-detail').onclick=()=>closeDetail(true);
$('refocus-poi').onclick=()=>{detailSheet.set('half');if(detailPOI)focusPOI(detailPOI);};
document.addEventListener('keydown',event=>{if(event.key==='Escape'&&$('detail').open){event.preventDefault();closeDetail(true);}});
$('detail').addEventListener('cancel',event=>{event.preventDefault();closeDetail(true);});
window.addEventListener('beforeunload',event=>{if(detailIsDirty()){event.preventDefault();event.returnValue='';}});

function evidencePanel(p){
  const id=p.id,number=value=>Number.isFinite(value)?value.toFixed(2):'unknown';
  const score=p.kind==='text'?`Detection / recognition score: ${number(p.score)}. This is not POI accuracy.`:'Experimental shape proposal; verify against the historical map.';
  return `<section id="evidence-panel" role="tabpanel" aria-labelledby="evidence-tab">
    <figure class="historic-evidence"><a href="/api/pois/${id}/image?kind=historic" target="_blank" rel="noopener"><img src="/api/pois/${id}/image?kind=historic" alt="Historical map with selected POI outlined in orange"></a><figcaption>Selected finding outlined · <a href="/api/pois/${id}/image?kind=historic" target="_blank" rel="noopener">Open full-size crop ↗</a></figcaption></figure>
    <p class="evidence-location">${p.lat.toFixed(6)} N · ${p.lon.toFixed(6)} E<br>Historical coordinates may be locally displaced.</p>
    <button class="primary annotate-shortcut">Annotate this POI</button>
    <details class="evidence-section" open><summary>Matches from map text and terrain</summary><section id="multi-evidence" class="osm-evidence" aria-live="polite"></section><p><a href="/evidence/multi-evidence/report.html" target="_blank" rel="noopener">Evaluation and suggested findings ↗</a> · <a href="/evidence/hollow-dot/report.html" target="_blank" rel="noopener">Historical symbol references ↗</a></p></details>
    <details class="evidence-section"><summary>Modern map and exclusion mask</summary><div class="comparison-images"><figure><img loading="lazy" src="/api/pois/${id}/image?kind=modern" alt="Modern NLSC map at the same extent"><figcaption>Modern NLSC</figcaption></figure><figure><img loading="lazy" src="/api/pois/${id}/image?kind=mask" alt="Red developed-area exclusion mask"><figcaption>Red = developed-area mask</figcaption></figure></div></details>
    <details class="evidence-section"><summary>Nearby OpenStreetMap objects</summary><section id="osm-evidence" class="osm-evidence"></section></details>
    <details class="evidence-section"><summary>Detector details and source records</summary><div class="detail-meta"><strong>${escapeHTML(p.disposition)}${p.reason?' · '+escapeHTML(p.reason):''}</strong><p>${score}<br>Algorithm: ${escapeHTML(p.spec.name)} · ${escapeHTML(p.spec.version)}<br>Raw OCR: <bdi>${escapeHTML(p.text||'(none)')}</bdi></p><pre>${escapeHTML(JSON.stringify({details:p.details,telemetry:p.telemetry,inputs:p.manifest},null,2))}</pre></div></details>
  </section>`;
}
async function openDetail(id){
  if(annotationDraft?.picking){await pickAnnotationFragment(id);return;}
  if(selectedId===id&&detailPOI){detailSheet.reveal();focusPOI(detailPOI);return;}
  if(!canLeaveDetail(()=>openDetail(id)))return;
  annotationCleanup();$('annotation-footer').hidden=true;$('annotation-status').textContent='';$('save-annotation').disabled=false;$('detail-osm-status').hidden=true;$('detail-osm-status').replaceChildren();
  const sequence=++detailSequence;selectedId=id;detailPOI=null;detailReturnFocus=id;detailSaved.clear();selectedOutline.clearLayers();
  hideMobileList();document.body.classList.add('detail-open');
  detailSheet.set('half');
  $('detail-title').textContent='Loading POI…';$('detail-subtitle').textContent=`POI #${id}`;
  $('detail-body').innerHTML='<p class="inspector-loading" role="status">Loading map evidence…</p>';
  $('refocus-poi').disabled=true;
  if(!$('detail').open)$('detail').show();
  map.invalidateSize({pan:false});
  try{
    const p=await api(`/api/pois/${id}`);
    if(sequence!==detailSequence)return;
    detailPOI=p;$('detail-title').textContent=label(p);$('detail-subtitle').textContent=`POI #${id} · ${p.source==='JM50K_1916'?'1916':'1924'} historical map`;
    $('detail-body').innerHTML=evidencePanel(p)+`<section id="annotation-panel" role="tabpanel" aria-labelledby="annotation-tab" hidden>${annotationEditor(p)}</section>`;
    bindAnnotationEditor(p);bindReadingSuggestions(p);bindVegetationEvidence(p);loadNearbyAnnotatedNames(p);loadOSMEvidence(p);loadMultiEvidence(p);
    markDetailSaved('annotation-editor');
    $('detail').querySelector('.annotate-shortcut').onclick=()=>showDetailTab('annotation');
    showDetailTab(detailTab);$('refocus-poi').disabled=false;focusPOI(p);$('detail-title').focus({preventScroll:true});
  }catch(e){if(sequence===detailSequence){$('detail-title').textContent='Evidence unavailable';$('detail-body').textContent=e.message;}}
}
let detailResizeTimer;
new ResizeObserver(()=>{
  clearTimeout(detailResizeTimer);
  if(detailPOI&&$('detail').open&&!$('detail').classList.contains('sheet-dragging'))detailResizeTimer=setTimeout(()=>{if(detailPOI&&$('detail').open)focusPOI(detailPOI);},120);
}).observe($('map'));
