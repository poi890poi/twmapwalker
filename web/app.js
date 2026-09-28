'use strict';
const $ = id => document.getElementById(id);
const escapeHTML = value => String(value ?? '').replace(/[&<>"']/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
let source = $('source').value, offset = 0, requestId = 0, paused = false, selectedId = null, latestItems = [], toastTimer;
const pageSize = 100;
const map = L.map('map', {zoomControl:false,minZoom:7,maxZoom:19,maxBounds:[[21.5,118],[26,123]],maxBoundsViscosity:1}).setView([24.859,121.559],15);
L.control.zoom({position:'topleft'}).addTo(map);
L.control.scale({position:'bottomright',imperial:false}).addTo(map);
const attribution = '<a href="https://gis.sinica.edu.tw/tileserver/" target="_blank">中央研究院 GIS</a> · <a href="https://maps.nlsc.gov.tw/" target="_blank">內政部國土測繪中心</a>';
const history = L.tileLayer(`/api/tiles/${source}/{z}/{x}/{y}`,{maxNativeZoom:16,minNativeZoom:5,attribution,keepBuffer:1}).addTo(map);
const modern = L.tileLayer('/api/tiles/EMAP/{z}/{x}/{y}',{maxNativeZoom:19,minNativeZoom:5,opacity:0,keepBuffer:1});
const markers = L.layerGroup().addTo(map), grid = L.layerGroup().addTo(map);
function bbox() {const b=map.getBounds();return [Math.max(118,b.getWest()),Math.max(21.5,b.getSouth()),Math.min(123,b.getEast()),Math.min(26,b.getNorth())];}
function toast(message) {$('toast').textContent=message;$('toast').hidden=false;clearTimeout(toastTimer);toastTimer=setTimeout(()=>$('toast').hidden=true,6000);}
async function api(url,options={}) {const response=await fetch(url,options);if(!response.ok){let message;try{message=(await response.json()).detail;}catch{message=response.statusText;}throw Error(typeof message==='string'?message:JSON.stringify(message));}return response.json();}
const post=(url,body)=>api(url,{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(body)});
function label(p) {return p.display_text||p.reading||p.text||(p.kind==='text'?'Unread text':p.kind==='trail'?'Dashed trail segment':'Unclassified symbol');}
async function refresh(reset=false) {
  document.querySelector('.sidebar').classList.toggle('searching',Boolean($('name-search').value));
  if(reset){offset=0;$('results').scrollTop=0;}
  const sequence=++requestId;
  try {
    const query=new URLSearchParams({bbox:bbox().join(','),source,disposition:$('excluded').checked?'all':'candidate',limit:pageSize,offset,q:$('name-search').value});
    const result=await api('/api/pois?'+query);
    if(sequence!==requestId)return;
    latestItems=result.items;markers.clearLayers();$('results').replaceChildren();$('result-count').textContent=result.total;
    $('search-message').textContent=result.search_message||'';$('search-message').hidden=!result.search_message;
    $('excluded-legend').hidden=!$('excluded').checked;
    $('page-label').textContent=result.total?`${offset+1}–${offset+result.items.length} of ${result.total}`:'No findings yet';
    $('prev').disabled=offset===0;$('next').disabled=offset+pageSize>=result.total;
    if(!result.items.length)$('results').innerHTML=$('name-search').value?'<div class="empty"><strong>No matching readings in this view.</strong><p>Try fewer known characters, use ? for an unknown character, or move the map. Unread regions without known characters cannot yet be matched to a name.</p></div>':'<div class="empty"><strong>No findings in this view yet.</strong><p>Move to a processed area or choose “Find in this area”. Discovery continues in the background.</p></div>';
    for(const item of result.items){
      const color=item.disposition==='excluded'?'#bb554c':item.kind==='text'?'#b9833b':item.kind==='trail'?'#7257a5':'#357d70';
      const geometry=JSON.parse(item.details).geometry; const marker=(geometry?L.polyline(geometry.coordinates.map(([lon,lat])=>[lat,lon]),{color,weight:4,dashArray:'6 5'}):L.circleMarker([item.lat,item.lon],{radius:item.kind==='text'?7:5,color:'#fff9ed',weight:1.6,fillColor:color,fillOpacity:.95})).addTo(markers);
      marker.bindTooltip(escapeHTML(label(item)),{direction:'top'});marker.on('click',()=>openDetail(item.id));
      const card=document.createElement('button');card.className='poi-card';
      card.innerHTML=`<img src="/api/pois/${item.id}/image?thumbnail=true" loading="lazy" alt="Historical map crop"><span class="content"><span class="poi-title">${escapeHTML(label(item))}</span><span class="poi-meta">${item.lat.toFixed(5)} N · ${item.lon.toFixed(5)} E</span><span class="tag ${item.disposition==='excluded'?'excluded':item.kind}">${item.disposition==='excluded'?'EXCLUDED':item.kind==='text'?'TEXT CANDIDATE':item.kind==='trail'?'TRAIL CANDIDATE':'SYMBOL CANDIDATE'}</span>${item.review?`<span class="tag review">${escapeHTML(item.review)}</span>`:''}</span>`;
      card.onclick=()=>{map.panTo([item.lat,item.lon]);openDetail(item.id);};$('results').append(card);
      if(item.search_match){const hint=document.createElement('span');hint.className='match-hint';hint.textContent=item.search_match.suggested_name?`${item.search_match.reason==='unknown-character'?'Unknown character':'Similar spelling'} · possible: ${item.search_match.suggested_name} (your search)`:item.search_match.reason==='unknown-character'?'Matches an unknown character':item.search_match.reason==='similar-spelling'?'Similar spelling':'Name match';card.querySelector('.content').append(hint);}
    }
    $('export').href='/api/export?'+new URLSearchParams({bbox:bbox().join(','),source,q:$('name-search').value});
    await refreshGrid();
  }catch(error){if(sequence===requestId)toast(error.message);}
}
let coverageSequence=0;
async function refreshGrid(){
  const sequence=++coverageSequence,selected=source,query=new URLSearchParams({bbox:bbox().join(','),source});
  const [coverage,result]=await Promise.all([api('/api/coverage-summary?'+query),$('grid').checked?api('/api/coverage?'+query):Promise.resolve([])]);
  if(sequence!==coverageSequence||selected!==source)return;
  $('view-coverage').textContent=`${coverage.complete} / ${coverage.total} tiles searched in this view`;
  $('view-coverage').classList.toggle('complete',coverage.complete===coverage.total);
  $('view-coverage').title=`${coverage.not_queued} not queued; ${coverage.queued_or_running} awaiting complete results. Unsearched areas may contain more landmarks.`;
  grid.clearLayers();if(!$('grid').checked)return;
  for(const t of result){L.rectangle(t.bounds.map(([lon,lat])=>[lat,lon]),{color:t.complete===t.total?'#39886e':'#b78037',weight:1,fillOpacity:.05}).bindTooltip(`${t.z}/${t.x}/${t.y} · ${t.complete}/${t.total} complete`).addTo(grid);}
}
async function status(){try{const s=await api('/api/status');paused=s.paused;const c=s.counts,total=Object.values(c).reduce((a,b)=>a+b,0),done=c.complete||0,remaining=(c.pending||0)+(c.running||0);$('job-badge').textContent=remaining;$('pause').textContent=paused?'Resume':'Pause';$('worker-label').textContent=paused?'Discovery paused':c.running?'Discovering map traces':c.pending?'Waiting for next job':c.failed?'Some jobs need attention':'Ready to explore';$('worker-detail').textContent=`${done} / ${total} runs complete · ${s.tiles} tiles${c.failed?' · '+c.failed+' failed':''}`;$('progress').style.width=(total?done/total*100:0)+'%';$('worker-dot').style.background=paused?'#ba9a61':'#75ae87';$('job-details').innerHTML=s.algorithms.map(a=>`<p><strong>${escapeHTML(a.name)}</strong> · ${escapeHTML(a.version)}<br><code>${a.fingerprint.slice(0,20)}</code></p>`).join('');if(!$('jobs-panel').hidden)await loadJobs();}catch(e){$('worker-label').textContent='Connection unavailable';$('worker-detail').textContent=e.message;}}
async function loadJobs(){const jobs=await api('/api/jobs');$('job-list').innerHTML=jobs.map(j=>`<div class="job-row"><strong>${escapeHTML(j.name)} · ${escapeHTML(j.state)}</strong><span>${escapeHTML(j.source)}<br>z${j.z} / ${j.x} / ${j.y} · attempts ${j.attempts}</span>${j.error?`<p class="error">${escapeHTML(j.error)}</p>`:''}</div>`).join('')||'<p>No work queued yet. Choose an area on the map.</p>';}
async function openDetail(id){selectedId=id;$('detail-title').textContent='Loading evidence…';$('detail-body').replaceChildren();if(!$('detail').open)$('detail').showModal();try{const p=await api(`/api/pois/${id}`);if(selectedId!==id)return;$('detail-title').textContent=label(p);const score=p.kind==='text'?(p.details.recognition==='not attempted'?`Unread region · detection score ${p.score.toFixed(2)}; no transcription attempted`:`OCR score ${p.score.toFixed(2)} (not POI accuracy)`):p.kind==='trail'?'Aligned dash chain; route continuity is not established':'Experimental shape proposal; not a classified map symbol';$('detail-body').innerHTML=`<div class="evidence-images"><figure><img src="/api/pois/${id}/image?kind=historic" alt="Historical tile with selected finding boxed"><figcaption>${escapeHTML(p.source)} · historical pixels</figcaption></figure><figure><img src="/api/pois/${id}/image?kind=modern" alt="Aligned modern NLSC map"><figcaption>Modern NLSC · same extent</figcaption></figure><figure><img src="/api/pois/${id}/image?kind=mask" alt="Red developed-area exclusion mask"><figcaption>Red = experimental developed-area mask</figcaption></figure></div><div class="detail-meta"><strong>${escapeHTML(p.disposition)}${p.reason?' · '+escapeHTML(p.reason):''}</strong><p>${score}<br>${p.lat.toFixed(6)} N, ${p.lon.toFixed(6)} E · zoom ${p.z}<br>${p.kind==='text'?'Detection rotation '+p.details.angle_degrees_ccw+'°; readings: '+escapeHTML((p.details.reading_candidates||[]).map(r=>r.text+' ('+r.direction+')').join(' / '))+'<br>':''}Historical coordinates may be locally displaced.<br>Developed overlap ${(p.details.developed_overlap*100).toFixed(1)}% · guarded interior ${((p.details.developed_interior_overlap||0)*100).toFixed(1)}%${p.details.boundary_review?' · BOUNDARY: RETAINED FOR REVIEW':''}${p.details.similar_components!==undefined?' · similar shapes '+p.details.similar_components:''}</p><code>Algorithm ${p.spec.name} · ${p.spec.version} · ${p.algorithm.slice(0,20)}</code></div>${readingEditor(p)}<div class="review-controls"><strong>Independent review</strong><p>Your assessment is stored separately from detection. Confirm only after inspecting the original map.</p><textarea id="review-note" rows="2" placeholder="Optional note: what does this text or symbol represent?" aria-label="Review note"></textarea><div class="review-actions"><button data-verdict="confirmed">Confirm finding</button><button data-verdict="rejected">Reject</button><button data-verdict="uncertain">Uncertain</button><span id="review-status">${p.reviews.length?'Last: '+escapeHTML(p.reviews.at(-1).verdict):'Not reviewed'}</span></div></div><details><summary>Input hashes, source URLs and timings</summary><pre>${escapeHTML(JSON.stringify({telemetry:p.telemetry,inputs:p.manifest},null,2))}</pre></details>`;bindReadingEditor(p);for(const button of document.querySelectorAll('[data-verdict]'))button.onclick=async()=>{try{await post(`/api/pois/${id}/review`,{verdict:button.dataset.verdict,note:$('review-note').value});$('review-status').textContent='Saved: '+button.dataset.verdict;refresh();}catch(e){toast(e.message);}};}catch(e){$('detail-title').textContent='Evidence unavailable';$('detail-body').textContent=e.message;}}
$('close-detail').onclick=()=>{$('detail').close();selectedId=null;};
$('detail').addEventListener('cancel',()=>selectedId=null);
$('source').onchange=()=>{source=$('source').value;history.setUrl(`/api/tiles/${source}/{z}/{x}/{y}`);refresh(true);};
$('opacity').oninput=()=>{const value=+$('opacity').value;$('opacity-value').textContent=value+'%';if(value&&!map.hasLayer(modern))modern.addTo(map);modern.setOpacity(value/100);if(!value&&map.hasLayer(modern))map.removeLayer(modern);};
$('home').onclick=()=>map.setView([24.859,121.559],15);
$('excluded').onchange=()=>refresh(true);$('grid').onchange=()=>refreshGrid().catch(e=>toast(e.message));
$('prev').onclick=()=>{offset=Math.max(0,offset-pageSize);refresh();};$('next').onclick=()=>{offset+=pageSize;refresh();};
$('scan').onclick=async()=>{const button=$('scan');button.disabled=true;try{const plan={bbox:bbox(),sources:[source]};const quote=await post('/api/plan/estimate',plan);if(!quote.allowed)throw Error(`${quote.tiles.toLocaleString()} tiles: zoom in to queue at most 2,500 tiles.`);const result=await post('/api/plan',plan);toast(result.added_jobs?`Queued ${result.added_jobs} runs across ${result.tiles} tiles at zoom 16.`:'This area is already recorded for the current algorithms.');await status();await refreshGrid();}catch(e){toast(e.message);}finally{button.disabled=false;}};
$('pause').onclick=async()=>{try{await post('/api/worker/pause',{paused:!paused});await status();toast(paused?'Paused. The current tile will finish safely.':'Background discovery resumed.');}catch(e){toast(e.message);}};
$('retry').onclick=async()=>{try{const r=await post('/api/worker/retry',{});toast(`${r.retried} jobs queued for retry.`);await status();}catch(e){toast(e.message);}};
for(const tab of ['discover','jobs'])$(tab+'-tab').onclick=()=>{for(const other of ['discover','jobs']){$(other+'-panel').hidden=other!==tab;$(other+'-tab').classList.toggle('active',other===tab);$(other+'-tab').setAttribute('aria-selected',String(other===tab));}if(tab==='jobs')loadJobs().catch(e=>toast(e.message));};
let mapTimer;map.on('moveend',()=>{clearTimeout(mapTimer);mapTimer=setTimeout(()=>refresh(true),180);});
let tileErrorAt=0;history.on('tileerror',()=>{if(Date.now()-tileErrorAt>30000){tileErrorAt=Date.now();toast('Some map tiles could not load. Check the map source or connection.');}});
status();refresh();setInterval(status,5000);setInterval(()=>{if(!$('detail').open)refresh();},15000);
