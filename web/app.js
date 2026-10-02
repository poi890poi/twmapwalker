'use strict';
const $ = id => document.getElementById(id);
const escapeHTML = value => String(value ?? '').replace(/[&<>"']/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
let source = $('source').value, offset = 0, requestId = 0, paused = false, selectedId = null, latestItems = [], toastTimer;
let viewMoving = false, areaSnapshot = null, browseSnapshot = null;
let pageSize = 50, totalResults = 0, browseController, markerSignature = '', mapEntries = [];
const restored=MapwalkerState.load(location.hash,()=>localStorage),saved=restored.params;
let comparisonEnabled=Number(saved.get('opacity'))>0;
const displayChoice=saved.get('display')||'top';if(['all','reduced','top','adaptive'].includes(displayChoice))$('display-level').value=displayChoice;
for (const id of ['source','kind','review','reading','sort','page-size','comparison','visibility']) {
  const value=saved.get(id); if(value && [...$(id).options].some(o=>o.value===value)) $(id).value=value;
}
$('name-search').value=(saved.get('q')||'').slice(0,80);$('excluded').checked=saved.get('excluded')==='1';
$('grid').checked=saved.get('grid')==='1';$('osm-context').checked=saved.get('osm')==='1';
source=$('source').value;pageSize=+$('page-size').value;
const savedPage=Number(saved.get('page'));offset=(Number.isInteger(savedPage)&&savedPage>0?Math.min(savedPage,100000)-1:0)*pageSize;
const map = L.map('map', {zoomControl:false,minZoom:5,maxZoom:19,preferCanvas:true,maxBounds:[[19,115],[29,126]],maxBoundsViscosity:.8});
const savedLat=Number(saved.get('lat')),savedLon=Number(saved.get('lon')),savedZoom=Number(saved.get('z'));
if(saved.has('lat')&&savedLat>=19&&savedLat<=29&&savedLon>=115&&savedLon<=126&&savedZoom>=5&&savedZoom<=19) map.setView([savedLat,savedLon],Math.round(savedZoom));
else map.fitBounds([[21.8,118.1],[26.35,122.1]],{padding:[35,50]});
L.control.zoom({position:'topleft'}).addTo(map);
const comparisonControl=L.control({position:'topleft'});
comparisonControl.onAdd=()=>{const button=L.DomUtil.create('button','comparison-switch');button.id='comparison-toggle';button.type='button';L.DomEvent.disableClickPropagation(button);L.DomEvent.disableScrollPropagation(button);return button;};
comparisonControl.addTo(map);
L.control.scale({position:'bottomright',imperial:false}).addTo(map);
const attribution = '<a href="https://gis.sinica.edu.tw/tileserver/" target="_blank">中央研究院 GIS</a> · <a href="https://maps.nlsc.gov.tw/" target="_blank">內政部國土測繪中心</a>';
const layerBounds=[[21.5,118],[26.5,123]];
const history = L.tileLayer(`/api/tiles/${source}/{z}/{x}/{y}`,{maxNativeZoom:16,minNativeZoom:5,attribution,keepBuffer:1,bounds:layerBounds,noWrap:true}).addTo(map);
const modern = L.tileLayer('/api/tiles/EMAP/{z}/{x}/{y}',{maxNativeZoom:19,minNativeZoom:5,keepBuffer:1,bounds:layerBounds,noWrap:true});
const rudyTiles=L.tileLayer('/api/rudy/tiles/{z}/{x}/{y}',{maxNativeZoom:19,minZoom:5,maxZoom:19,keepBuffer:1,bounds:layerBounds,noWrap:true,attribution:'<a href="https://rudymap.tw/">Rudy · MOI.OSM</a> · &copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap contributors</a> · Elevate / Tobias Kühn · bochengsiong · <a href="https://creativecommons.org/licenses/by-nc-sa/3.0/">CC BY-NC-SA 3.0 style</a>'});
const osmTiles=L.tileLayer('https://tile.openstreetmap.org/{z}/{x}/{y}.png',{maxNativeZoom:19,minZoom:5,maxZoom:19,keepBuffer:1,bounds:layerBounds,noWrap:true,attribution:'&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap contributors</a>'});
const grid = L.layerGroup().addTo(map), trails=L.layerGroup().addTo(map);
function groupIcon(count,annotated=0) {return L.divIcon({className:'poi-cluster',html:`<div role="img" aria-label="${count} findings, ${annotated} annotated"><span aria-hidden="true">${count.toLocaleString()}</span>${annotated?`<small aria-hidden="true" class="cluster-annotations" title="${annotated} of ${count} annotated">✎ ${annotated.toLocaleString()}</small>`:''}</div>`,iconSize:[36,36]});}
const markers = L.markerClusterGroup({maxClusterRadius:zoom=>zoom<13?40:zoom<16?24:16,showCoverageOnHover:false,zoomToBoundsOnClick:false,
  removeOutsideVisibleBounds:true,animate:false,spiderfyOnMaxZoom:false,
  iconCreateFunction:cluster=>{const children=cluster.getAllChildMarkers();return groupIcon(children.reduce((sum,m)=>sum+m.options.poiCount,0),children.reduce((sum,m)=>sum+(m.options.annotatedCount||0),0));}}).addTo(map);
function bbox() {const b=map.getBounds(),v=[Math.max(118,b.getWest()),Math.max(21.5,b.getSouth()),Math.min(123,b.getEast()),Math.min(26.5,b.getNorth())];return v[0]<v[2]&&v[1]<v[3]?v:null;}
function dismissToast() {clearTimeout(toastTimer);$('toast').hidden=true;}
function toast(message) {$('toast-message').textContent=String(message).slice(0,180);$('toast').hidden=false;clearTimeout(toastTimer);toastTimer=setTimeout(dismissToast,6000);}
$('dismiss-toast').onclick=dismissToast;
async function api(url,options={}) {
  const response=await accessFetch(url,options);
  if(response.status===401){requireSignIn();throw Error('Please sign in again.');}
  if(!response.ok){let message;try{message=(await response.json()).detail;}catch{message=response.statusText;}throw Error(MapwalkerView.error(message,response.status));}return response.json();
}
const post=(url,body)=>api(url,{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(body)});
function label(p) {return p.label||p.display_text||p.reading||p.text||(p.kind==='text'?'Unread text':p.kind==='trail'?'Dashed trail segment':'Unclassified symbol');}
function areaKey(){return source+':'+(bbox()?.join(',')||'');}
function currentQuery() {return new URLSearchParams({bbox:bbox()?.join(',')||'',source,disposition:$('excluded').checked?'all':'candidate',q:$('name-search').value,kind:$('kind').value,visibility:$('visibility').value,review:$('review').value,reading:$('reading').value,sort:$('sort').value,display:$('display-level').value,display_zoom:MapwalkerView.zoom(map.getZoom()),include_trails:false});}
function saveView(remember=true) {
  const center=map.getCenter(),params=new URLSearchParams({lat:center.lat.toFixed(6),lon:center.lng.toFixed(6),z:MapwalkerView.zoom(map.getZoom()),source,kind:$('kind').value,visibility:$('visibility').value,review:$('review').value,reading:$('reading').value,sort:$('sort').value,'page-size':pageSize,page:Math.floor(offset/pageSize)+1,display:$('display-level').value});
  if($('name-search').value)params.set('q',$('name-search').value);
  if($('excluded').checked)params.set('excluded','1');
  params.set('opacity',comparisonEnabled?'100':'0');params.set('comparison',$('comparison').value);if($('osm-context').checked)params.set('osm','1');
  if($('grid').checked)params.set('grid','1');
  window.history.replaceState(null,'','#'+params);
  if(remember&&!document.hidden)MapwalkerState.save(params,{list:document.body.classList.contains('show-list'),layers:document.body.classList.contains('map-tools-open'),filters:$('sidebar').classList.contains('filters-open'),jobs:!$('jobs-panel').hidden},()=>localStorage);
  $('map-position').textContent=`${center.lat.toFixed(4)}° N · ${center.lng.toFixed(4)}° E · z${MapwalkerView.zoom(map.getZoom())}`;
}
function focusGroup(entries,cluster) {
  // Small groups expose real members immediately, even below maximum zoom.
  if(cluster && entries.length<=12 && entries.every(m=>m.options.poiCount===1)){cluster.spiderfy();return;}
  const bounds=L.latLngBounds([]);for(const m of entries){const b=m.options.poiBounds;bounds.extend([b[1],b[0]]);bounds.extend([b[3],b[2]]);}
  if(MapwalkerView.zoom(map.getZoom())===19){if(cluster)cluster.spiderfy();else toast('Maximum zoom. Every finding in this area is available in the paged list.');return;}
  const target=Math.min(19,Math.max(MapwalkerView.zoom(map.getZoom())+1,map.getBoundsZoom(bounds,false,L.point(90,90))));
  map.setView(bounds.getCenter(),target);
}
markers.on('clusterclick',e=>focusGroup(e.layer.getAllChildMarkers(),e.layer));
function renderTrails() {
  trails.clearLayers();if(map.getZoom()<15)return;
  for(const {marker,point} of mapEntries)if(point?.geometry && markers.getVisibleParent(marker)===marker){
    L.polyline(point.geometry.coordinates.map(([lon,lat])=>[lat,lon]),{color:'#7257a5',weight:4,dashArray:'6 5'})
      .bindTooltip(escapeHTML(label(point))).on('click',()=>openDetail(point.id)).addTo(trails);
  }
}
markers.on('animationend spiderfied unspiderfied',renderTrails);
function renderMap(data) {
  const signature=JSON.stringify(data);if(signature===markerSignature){renderTrails();return;}
  markerSignature=signature;markers.clearLayers();trails.clearLayers();mapEntries=[];
  const layers=[];
  for(const entry of data.items){
    const point=data.mode==='points'?entry:entry.count===1?entry.item:null;
    const count=point?1:entry.count,bounds=point?point.bounds:entry.bounds,annotated=point?Number(!!point.annotated):entry.annotated_count||0;
    const description=point?`${label(point)} · ${point.annotated?'Annotated':'Not annotated'}`:`${count.toLocaleString()} findings · ${annotated.toLocaleString()} annotated`;
    let icon;
    if(point){const color=point.disposition==='excluded'?'excluded':point.kind;
      icon=L.divIcon({className:`poi-pin ${color}${point.annotated?' annotated':''}`,html:point.annotated?'<span aria-hidden="true">✎</span>':'<span></span>',iconSize:[28,28]});
    }else icon=groupIcon(count,annotated);
    const marker=L.marker([entry.lat,entry.lon],{icon,poiCount:count,annotatedCount:annotated,poiBounds:bounds,keyboard:true,title:description});
    marker.bindTooltip(escapeHTML(description)+(point?'':' · '+escapeHTML(Object.entries(entry.kinds).map(([k,v])=>`${v} ${k}`).join(', '))));
    marker.on('click',()=>point?openDetail(point.id):focusGroup([marker]));layers.push(marker);mapEntries.push({marker,point});
  }
  markers.addLayers(layers);renderTrails();
}
function renderList(result) {
  latestItems=result.items;totalResults=result.total;offset=result.offset;
  $('results').replaceChildren();$('result-count').textContent=result.total.toLocaleString();
  $('search-message').textContent=result.search_message||'';$('search-message').hidden=!result.search_message;
  $('excluded-legend').hidden=!$('excluded').checked;
  const pages=Math.max(1,Math.ceil(result.total/pageSize));$('page-number').value=Math.floor(offset/pageSize)+1;$('page-number').max=pages;
  $('page-total').textContent=`of ${pages.toLocaleString()}`;
  $('page-label').textContent=result.total?`${(offset+1).toLocaleString()}–${(offset+result.items.length).toLocaleString()} of ${result.total.toLocaleString()} findings`:'No findings';
  $('prev').disabled=offset===0;$('next').disabled=offset+pageSize>=result.total;$('page-number').disabled=!result.total;
  if(!result.items.length)$('results').innerHTML='<div class="empty"><strong>No matching findings in this view.</strong><p>Try All candidates, clear filters, or move to Wulai. Unread text cannot match a name until some characters are known.</p></div>';
  for(const item of result.items){
    const card=document.createElement('button');card.className='poi-card';card.dataset.poiId=item.id;
    card.innerHTML=`<img src="/api/pois/${item.id}/image?thumbnail=true" loading="lazy" alt="Historical map crop"><span class="content"><span class="poi-title" dir="auto">${escapeHTML(label(item))}</span><span class="poi-meta">${item.lat.toFixed(5)} N · ${item.lon.toFixed(5)} E</span><span class="tag ${item.disposition==='excluded'?'excluded':item.kind}">${item.disposition==='excluded'?'EXCLUDED':item.kind==='text'?'TEXT CANDIDATE':item.kind==='trail'?'TRAIL CANDIDATE':'SYMBOL CANDIDATE'}</span>${item.hidden?'<span class="tag review">HIDDEN</span>':''}${item.review?`<span class="tag review">${escapeHTML(item.review==='other'?'Other':item.review)}</span>`:''}</span>`;
    card.onclick=()=>openDetail(item.id);$('results').append(card);
    if(item.search_match){const hint=document.createElement('span');hint.className='match-hint';hint.textContent=item.search_match.suggested_name?`${item.search_match.reason==='unknown-character'?'Unknown character':'Similar spelling'} · possible: ${item.search_match.suggested_name} (your search)`:item.search_match.reason==='unknown-character'?'Matches an unknown character':item.search_match.reason==='similar-spelling'?'Similar spelling':'Name match';card.querySelector('.content').append(hint);}
  }
}
async function refresh(reset=false,remember=true) {
  if(viewMoving)return;
  if(reset){offset=0;$('results').scrollTop=0;}
  const sequence=++requestId;browseController?.abort();browseController=new AbortController();
  $('browse-status').textContent='Updating this view…';$('results').setAttribute('aria-busy','true');$('export').removeAttribute('href');
  saveView(remember);updateDiscovery();
  if(!bbox()){
    renderList({total:0,items:[],offset:0});renderMap({total:0,items:[],mode:'points'});
    $('browse-status').textContent='Outside the Taiwan map region.';$('map-count').textContent='Outside coverage';$('display-summary').textContent='0 shown';$('view-coverage').textContent='Return to Taiwan to explore';
    grid.clearLayers();$('results').setAttribute('aria-busy','false');return;
  }
  try {
    const query=currentQuery();query.set('limit',pageSize);query.set('offset',offset);query.set('zoom',MapwalkerView.zoom(map.getZoom()));
    const result=await api('/api/browse?'+query,{signal:browseController.signal});
    if(sequence!==requestId)return;
    renderList(result);renderMap(result.map);browseSnapshot={key:currentQuery().toString(),result};updateDiscovery();
    const available=result.display.available,hidden=result.display.hidden;
    $('display-summary').textContent=hidden?`${result.total.toLocaleString()} / ${available.toLocaleString()}`:`${result.total.toLocaleString()} shown`;
    $('display-summary').title=`${hidden.toLocaleString()} proposals hidden by display level. Choose All candidates to see them.`;
    $('map-count').textContent=hidden?`${result.total.toLocaleString()} of ${available.toLocaleString()} shown · zoom in for more`:`${result.total.toLocaleString()} mapped · tap groups to explore`;
    $('map-count').dataset.total=result.map.total;
    $('browse-status').textContent='';$('results').setAttribute('aria-busy','false');
    $('export').href='/api/export?'+currentQuery();saveView(remember);
    refreshGrid().catch(()=>{$('view-coverage').textContent='Tile progress unavailable';});
  }catch(error){if(sequence===requestId&&error.name!=='AbortError'){
    markers.clearLayers();trails.clearLayers();markerSignature='';$('results').replaceChildren();$('result-count').textContent='—';
    $('browse-status').textContent='Unable to load this view. ';const retry=document.createElement('button');retry.textContent='Retry';retry.onclick=()=>refresh();$('browse-status').append(retry);
    $('display-summary').textContent='Unavailable';$('map-count').textContent='Findings unavailable';delete $('map-count').dataset.total;
    $('results').setAttribute('aria-busy','false');$('prev').disabled=true;$('next').disabled=true;toast(error.message);
  }}
}
let coverageSequence=0;
async function refreshGrid(){
  if(!bbox()||viewMoving)return;
  const key=areaKey(),sequence=++coverageSequence,selected=source,query=new URLSearchParams({bbox:bbox().join(','),source});
  const [coverage,result]=await Promise.all([api('/api/coverage-summary?'+query),$('grid').checked&&map.getZoom()>=13?api('/api/coverage?'+query):Promise.resolve([])]);
  if(sequence!==coverageSequence||selected!==source||key!==areaKey())return;
  areaSnapshot={key,value:coverage};updateDiscovery();
  $('view-coverage').textContent=`${coverage.complete.toLocaleString()} / ${coverage.total.toLocaleString()} tiles complete in this view`+(coverage.blank_tiles?` · ${coverage.blank_tiles} blank ignored`:'');
  $('view-coverage').classList.toggle('complete',coverage.complete===coverage.total);
  $('view-coverage').title=`${coverage.not_queued} not queued; ${coverage.queued_or_running} awaiting complete results. Unsearched areas may contain more landmarks.`;
  grid.clearLayers();if(!$('grid').checked)return;if(map.getZoom()<13){$('view-coverage').textContent+=' · zoom in for tile outlines';return;}
  for(const t of result){L.rectangle(t.bounds.map(([lon,lat])=>[lat,lon]),{color:t.complete===t.total?'#39886e':'#b78037',weight:1,fillOpacity:.05}).bindTooltip(`${t.z}/${t.x}/${t.y} · ${t.complete}/${t.total} complete`).addTo(grid);}
}
function updateDiscovery(){
  const area=areaSnapshot?.key===areaKey()?areaSnapshot.value:null;
  if(!area){$('worker-label').textContent=bbox()?'Checking this view…':'Outside Taiwan coverage';$('worker-detail').textContent='';$('worker-current').textContent='';$('view-message').hidden=true;$('progress').style.width='0%';document.querySelector('.progress-track').setAttribute('aria-valuenow','0');return;}
  const state=MapwalkerView.discovery(area);
  $('worker-label').textContent=state.title;$('worker-detail').textContent=state.detail;$('worker-current').textContent=state.current;
  $('progress').style.width=state.percent+'%';document.querySelector('.progress-track').setAttribute('aria-valuenow',state.percent);
  const result=browseSnapshot?.key===currentQuery().toString()?browseSnapshot.result:null;
  const hasFilters=$('visibility').value!=='visible'||!!$('name-search').value.trim()||['kind','review','reading'].some(id=>$(id).value!=='all');
  const hint=MapwalkerView.empty(area,result,hasFilters);
  $('view-message').hidden=!hint.message;$('view-message-text').textContent=hint.message;
  $('view-message-action').hidden=!hint.action;$('view-message-action').dataset.action=hint.action;
  $('view-message-action').textContent=({all:'Show all candidates',filters:'Clear filters',excluded:'View excluded',hidden:'Show hidden features',jobs:'Background work'})[hint.action]||'';
  if(result && !result.total){const empty=$('results').querySelector('.empty');if(empty)empty.textContent=hint.message||'No matching findings in this view.';}
}
$('view-message-action').onclick=()=>{
  const action=$('view-message-action').dataset.action;
  if(action==='all'){$('display-level').value='all';$('display-level').onchange();}
  if(action==='hidden'){$('visibility').value='hidden';$('visibility').onchange();filterSummary();}
  if(action==='excluded'){$('excluded').checked=true;$('display-level').value='all';filterSummary();$('display-level').onchange();}
  if(action==='filters')$('reset-filters').click();
  if(action==='jobs'){if(!document.body.classList.contains('show-list'))$('toggle-list').click();$('jobs-tab').click();}
};
async function status(){try{
  const s=await api('/api/status');paused=s.paused;const c=s.counts,remaining=(c.pending||0)+(c.running||0);
  $('job-badge').textContent=remaining;$('pause').textContent=paused?'Resume':'Pause';$('worker-dot').style.background=paused?'#ba9a61':'#75ae87';
  $('job-details').innerHTML=`<p><strong>All queued areas</strong> · ${(c.complete||0).toLocaleString()} checks complete · ${remaining.toLocaleString()} waiting/running · ${c.failed||0} failed</p>`+s.algorithms.map(a=>`<p><strong>${escapeHTML(a.name)}</strong> · ${escapeHTML(a.version)}<br><code>${a.fingerprint.slice(0,20)}</code></p>`).join('');
  const previous=areaSnapshot;
  await refreshGrid();
  if(previous && areaSnapshot?.key===previous.key && areaSnapshot.value.checks.complete!==previous.value.checks.complete && !viewMoving)refresh(false,false);
  if(!$('jobs-panel').hidden)await loadJobs();
}catch(e){$('worker-label').textContent='Progress unavailable';$('worker-detail').textContent='Connection interrupted. Retrying…';$('worker-current').textContent='';}}
async function loadJobs(){const jobs=await api('/api/jobs');$('job-list').innerHTML=jobs.map(j=>`<div class="job-row"><strong>${escapeHTML(j.name)} · ${escapeHTML(j.state)}</strong><span>${escapeHTML(j.source)}<br>z${j.z} / ${j.x} / ${j.y} · attempts ${j.attempts}</span>${j.error?`<p class="error">${escapeHTML(j.error)}</p>`:''}</div>`).join('')||'<p>No work queued yet. Choose an area on the map.</p>';}
$('source').onchange=()=>{const nextSource=$('source').value;if(!canLeaveDetail(()=>{$('source').value=nextSource;$('source').onchange();})){$('source').value=source;return;}closeDetail(false);source=$('source').value;history.setUrl(`/api/tiles/${source}/{z}/{x}/{y}`);refresh(true);scheduleFocus();};
function applyComparison(){
  const kind=$('comparison').value,chosen={osm:osmTiles,nlsc:modern,rudy:rudyTiles}[kind];
  for(const layer of [modern,osmTiles,rudyTiles])if(layer!==chosen||!comparisonEnabled)map.removeLayer(layer);
  chosen.setOpacity(1);if(comparisonEnabled&&!map.hasLayer(chosen))chosen.addTo(map);
  const button=$('comparison-toggle'),name={nlsc:'Modern map',osm:'OSM map',rudy:'Rudy map'}[kind];
  button.textContent=`${name}: ${comparisonEnabled?'On':'Off'}`;button.setAttribute('aria-pressed',String(comparisonEnabled));
  button.title=comparisonEnabled?'Turn off to see the historical map':`Show ${$('comparison').selectedOptions[0].textContent} at full opacity`;
}
$('comparison-toggle').onclick=()=>{comparisonEnabled=!comparisonEnabled;applyComparison();saveView();};
$('comparison').onchange=()=>{comparisonEnabled=true;applyComparison();saveView();};
osmTiles.on('tileerror',()=>toast('An OpenStreetMap tile could not load. The historical layer remains available.'));
let rudyErrorAt=0;rudyTiles.on('tileerror',()=>{if(Date.now()-rudyErrorAt>30000){rudyErrorAt=Date.now();toast('Rudy map could not load. Check that the local map and renderer are installed.');}});
$('home').onclick=()=>{hideMobileList();map.setView([24.859,121.559],15);};
$('excluded').onchange=()=>refresh(true);$('grid').onchange=()=>{saveView();refreshGrid().catch(e=>toast(e.message));};
$('prev').onclick=()=>{offset=Math.max(0,offset-pageSize);$('results').scrollTop=0;refresh();};$('next').onclick=()=>{offset+=pageSize;$('results').scrollTop=0;refresh();};
$('scan').onclick=async()=>{const button=$('scan');button.disabled=true;try{if(!bbox())throw Error('Return to Taiwan to select an area.');const plan={bbox:bbox(),sources:[source]};const quote=await post('/api/plan/estimate',plan);if(!quote.allowed)throw Error(`${quote.tiles.toLocaleString()} tiles: zoom in to queue at most 2,500 tiles.`);const result=await post('/api/plan',plan);toast(result.message);await status();await refreshGrid();}catch(e){toast(e.message);}finally{button.disabled=false;}};
$('pause').onclick=async()=>{try{await post('/api/worker/pause',{paused:!paused});await status();toast(paused?'Paused. The current tile will finish safely.':'Background discovery resumed.');}catch(e){toast(e.message);}};
$('retry').onclick=async()=>{try{const r=await post('/api/worker/retry',{});toast(`${r.retried} jobs queued for retry.`);await status();}catch(e){toast(e.message);}};
for(const tab of ['discover','jobs'])$(tab+'-tab').onclick=()=>{for(const other of ['discover','jobs']){$(other+'-panel').hidden=other!==tab;$(other+'-tab').classList.toggle('active',other===tab);$(other+'-tab').setAttribute('aria-selected',String(other===tab));}saveView();if(tab==='jobs')loadJobs().catch(e=>toast(e.message));};
let focusTimer,focusBusy=false,focusWanted=null;
function scheduleFocus(){
  clearTimeout(focusTimer);
  focusTimer=setTimeout(()=>{if(document.hidden||viewMoving||!bbox())return;focusWanted={bbox:bbox(),source};sendFocus();},600);
}
async function sendFocus(){
  if(focusBusy)return;
  focusBusy=true;
  try{while(focusWanted){const view=focusWanted;focusWanted=null;await post('/api/view',view);if(!focusWanted&&!viewMoving)await refreshGrid();}}
  catch(error){toast('View priority could not update. '+error.message);}
  finally{focusBusy=false;if(focusWanted)sendFocus();}
}
let lastPosition=map.getCenter().toString()+':'+map.getZoom();
let mapTimer;map.on('movestart',()=>{clearTimeout(focusTimer);focusWanted=null;viewMoving=true;areaSnapshot=null;browseSnapshot=null;updateDiscovery();dismissToast();requestId++;coverageSequence++;browseController?.abort();$('export').removeAttribute('href');});map.on('moveend',()=>{viewMoving=false;const position=map.getCenter().toString()+':'+map.getZoom(),changed=position!==lastPosition;lastPosition=position;clearTimeout(mapTimer);if(changed){offset=0;saveView();}mapTimer=setTimeout(()=>refresh(changed,changed),180);scheduleFocus();});
document.addEventListener('visibilitychange',()=>{if(!document.hidden)scheduleFocus();});
scheduleFocus();
let tileErrorAt=0;history.on('tileerror',()=>{if(Date.now()-tileErrorAt>30000){tileErrorAt=Date.now();toast('Some map tiles could not load. Check the map source or connection.');}});

for(const id of ['kind','review','reading','sort'])$(id).onchange=()=>refresh(true);
$('review').onchange=()=>{if(['other','rejected'].includes($('review').value)){$('visibility').value='all';$('display-level').value='all';$('excluded').checked=true;}refresh(true);};
$('visibility').onchange=()=>{if($('visibility').value!=='visible'){$('display-level').value='all';$('excluded').checked=true;}refresh(true);};
$('page-size').onchange=()=>{pageSize=+$('page-size').value;refresh(true);};
$('page-number').onchange=()=>{const page=Number($('page-number').value);if(!Number.isInteger(page)||page<1){$('page-number').value=Math.floor(offset/pageSize)+1;return;}offset=(Math.min(page,Math.max(1,Math.ceil(totalResults/pageSize)))-1)*pageSize;$('results').scrollTop=0;refresh();};
$('page-number').onkeydown=event=>{if(event.key==='Enter'){event.preventDefault();$('page-number').onchange();}};
$('reset-filters').onclick=()=>{for(const id of ['kind','review','reading'])$(id).value='all';$('visibility').value='visible';$('sort').value='priority';$('name-search').value='';$('excluded').checked=false;refresh(true);};
$('taiwan').onclick=()=>{hideMobileList();map.fitBounds([[21.8,118.1],[26.35,122.1]],{padding:[35,50]});};
$('place').onchange=()=>{if(!$('place').value)return;const [lat,lon,z]=$('place').value.split(',').map(Number);hideMobileList();map.setView([lat,lon],z);$('place').value='';};
$('share-view').onclick=async()=>{saveView();try{await navigator.clipboard.writeText(location.href);toast('View link copied, including filters and page.');}catch{toast('Copy the address from your browser to share this view.');}};
function hideMobileList(){document.body.classList.remove('show-list');$('toggle-list').textContent='POI list';$('toggle-list').setAttribute('aria-expanded','false');map.invalidateSize();}
$('toggle-list').onclick=()=>{if($('detail').open){closeDetail(true);return;}const open=document.body.classList.toggle('show-list');$('toggle-list').textContent=open?'Show map':'POI list';$('toggle-list').setAttribute('aria-expanded',String(open));if(!open)map.invalidateSize();saveView();};
$('map-tools-toggle').onclick=()=>{const open=document.body.classList.toggle('map-tools-open');$('map-tools-toggle').setAttribute('aria-expanded',String(open));$('map-tools-toggle').textContent=open?'Close layers':'Layers & places';saveView();};
$('toggle-filters').onclick=()=>{const open=$('sidebar').classList.toggle('filters-open');$('toggle-filters').setAttribute('aria-expanded',String(open));saveView();};
function filterSummary(){const active=['kind','review','reading'].filter(id=>$(id).value!=='all').length+Number($('excluded').checked)+Number($('visibility').value!=='visible');$('toggle-filters').textContent=`Filter & sort${active?' · '+active+' active':''}`;}
for(const id of ['kind','review','reading','excluded','sort','visibility'])$(id).addEventListener('change',filterSummary);
$('reset-filters').addEventListener('click',filterSummary);filterSummary();
applyComparison();
// Restore layout after handlers exist, before initial requests save the snapshot.
if(restored.ui.list){document.body.classList.add('show-list');$('toggle-list').textContent='Show map';$('toggle-list').setAttribute('aria-expanded','true');}
if(restored.ui.layers){document.body.classList.add('map-tools-open');$('map-tools-toggle').textContent='Close layers';$('map-tools-toggle').setAttribute('aria-expanded','true');}
if(restored.ui.filters){$('sidebar').classList.add('filters-open');$('toggle-filters').setAttribute('aria-expanded','true');}
if(restored.ui.jobs){for(const tab of ['discover','jobs']){$(tab+'-panel').hidden=tab!=='jobs';$(tab+'-tab').classList.toggle('active',tab==='jobs');$(tab+'-tab').setAttribute('aria-selected',String(tab==='jobs'));}loadJobs().catch(e=>toast(e.message));}
new ResizeObserver(()=>map.invalidateSize({pan:false})).observe($('map'));
status();refresh();setInterval(status,5000);setInterval(()=>{if(!$('detail').open&&!document.hidden&&!browseController?.signal.aborted)refresh(false,false);},30000);

$('display-level').onchange=()=>{try{localStorage.setItem('mapwalker-display',$('display-level').value);}catch{}refresh(true);};

new ResizeObserver(entries=>{const height=entries[0].borderBoxSize?.[0]?.blockSize||entries[0].target.getBoundingClientRect().height;document.querySelector('.map-shell').style.setProperty('--workbar-height',Math.ceil(height)+'px');}).observe(document.querySelector('.workbar'));
