'use strict';
// OSM is an independent, modern evidence layer. Never mix its features into
// historical POI counts, labels, confidence scores or review records.
const osmContextLayer=L.layerGroup();
const osmAttribution='OSM context © <a href="https://www.openstreetmap.org/copyright">OpenStreetMap contributors</a>';
let osmHasAttribution=false;
let osmMapSequence=0,osmMapTimer,osmEvidenceTimer,osmLastView='';
function osmDate(value){return value?new Date(value*1000).toLocaleString():'not yet retrieved';}
function osmSummary(p){const tags=p.tags;return [p.category,tags.historic,tags.natural,tags.highway,tags.waterway,tags.amenity,tags.tourism].filter(Boolean).join(' · ');}
function osmLinks(p){return `<a href="${escapeHTML(p.url)}" target="_blank" rel="noopener">${escapeHTML(p.name||osmSummary(p))} ↗</a>`;}
async function refreshOSM(force=false){
  const enabled=$('osm-context').checked,center=map.getCenter();
  if(enabled&&!osmHasAttribution){map.attributionControl.addAttribution(osmAttribution);osmHasAttribution=true;}
  if(!enabled&&osmHasAttribution){map.attributionControl.removeAttribution(osmAttribution);osmHasAttribution=false;}
  $('osm-map-status').hidden=!enabled;
  if(!enabled){osmMapSequence++;clearTimeout(osmMapTimer);osmLastView='';osmContextLayer.clearLayers();map.removeLayer(osmContextLayer);return;}
  if(map.getZoom()<14||center.lng<118||center.lng>123||center.lat<21.5||center.lat>26.5){
    osmMapSequence++;clearTimeout(osmMapTimer);osmLastView='';osmContextLayer.clearLayers();$('osm-map-status').textContent='Zoom in to see mountain context.';return;
  }
  const view=`${center.lng.toFixed(5)},${center.lat.toFixed(5)}`;if(view===osmLastView&&!force)return;osmLastView=view;
  const sequence=++osmMapSequence;clearTimeout(osmMapTimer);osmContextLayer.clearLayers();$('osm-map-status').textContent='Loading OSM context…';
  try{
    const result=await api('/api/osm/context?'+new URLSearchParams({lon:center.lng,lat:center.lat}));
    if(sequence!==osmMapSequence)return;
    if(!map.hasLayer(osmContextLayer))osmContextLayer.addTo(map);
    L.circle(center,{radius:result.radius_m,color:'#287cb0',weight:1,fillOpacity:.015,interactive:false}).addTo(osmContextLayer);
    L.geoJSON({type:'FeatureCollection',features:result.features},{
      style:()=>({color:'#287cb0',weight:3,opacity:.85,dashArray:'4 3'}),
      pointToLayer:(feature,latlng)=>L.circleMarker(latlng,{radius:5,color:'#fff',weight:1.5,fillColor:'#287cb0',fillOpacity:.9}),
      onEachFeature:(feature,layer)=>{const p=feature.properties;layer.bindTooltip('OSM · '+escapeHTML(p.name||osmSummary(p)));layer.bindPopup(`<strong>OSM supporting context</strong><p>${osmLinks(p)}<br>${escapeHTML(osmSummary(p))}<br>Approximately ${p.distance_m} m from map center.</p><small>Modern data; historical identity is unconfirmed.</small>`);}
    }).addTo(osmContextLayer);
    $('osm-map-status').textContent=result.state==='failed'?`OSM unavailable. ${result.features.length?'Showing cached context. ':''}Retry after ${osmDate(result.retry_at)}.`:
      result.state!=='complete'?'Fetching OSM in the background…':`Blue: ${result.features.length}${result.truncated?' of '+result.total:''} nearby OSM features · ${result.radius_m} m radius.`;
    if(result.state==='pending'||result.state==='running')osmMapTimer=setTimeout(()=>refreshOSM(true),5000);
  }catch(error){if(sequence===osmMapSequence){osmLastView='';$('osm-map-status').textContent='OSM context unavailable: '+error.message;}}
}
async function loadOSMEvidence(p){
  clearTimeout(osmEvidenceTimer);const host=$('osm-evidence');if(!host)return;
  host.innerHTML='<h3>OSM supporting evidence</h3><p>Checking nearby trails, mountain landmarks and historical features…</p>';
  async function update(){
    try{
      const result=await api('/api/osm/context?'+new URLSearchParams({lon:p.lon,lat:p.lat}));
      if(selectedId!==p.id||!$('detail').open)return;
      host.innerHTML=`<h3>OSM supporting evidence</h3><p>${escapeHTML(result.note)} Search radius: ${result.radius_m} m.</p><p class="osm-source"><a href="https://www.openstreetmap.org/copyright" target="_blank" rel="noopener">© OpenStreetMap contributors · ODbL</a> · Retrieved ${escapeHTML(osmDate(result.retrieved_at))}${result.stale?' · cache refreshing / unavailable':''}</p>`;
      if(result.state==='pending'||result.state==='running'){
        host.insertAdjacentHTML('beforeend','<p role="status">Fetching structured OSM data in the background. You can keep exploring.</p>');
        osmEvidenceTimer=setTimeout(update,5000);
      }else if(result.state==='failed')host.insertAdjacentHTML('beforeend',`<p role="status">OSM context unavailable: ${escapeHTML(result.error)}. Retry after ${escapeHTML(osmDate(result.retry_at))}.</p>`);
      if(result.state==='complete'&&!result.total)host.insertAdjacentHTML('beforeend','<p>No mapped OSM features from the selected categories within this radius. This does not establish that historical landmarks are absent.</p>');
      if(result.features.length){
        host.insertAdjacentHTML('beforeend',`<p>${result.total} nearby features${result.total>20?' · closest 20 shown':''}. Distances are approximate distances to OSM geometry, without displacement correction.</p>`);
        const list=document.createElement('div');list.className='osm-evidence-list';
        for(const feature of result.features.slice(0,20)){
          const f=feature.properties,card=document.createElement('details');
          card.innerHTML=`<summary><strong>${escapeHTML(f.name||osmSummary(f))}</strong><span>~${f.distance_m} m · ${escapeHTML(f.category)}</span></summary><p>${osmLinks(f)} · ${escapeHTML(f.osm_type)} ${f.osm_id}</p><dl>${Object.entries(f.tags).map(([k,v])=>`<dt>${escapeHTML(k)}</dt><dd>${escapeHTML(v)}</dd>`).join('')}</dl>`;
          list.append(card);
        }
        host.append(list);
      }
      if(result.sha256)host.insertAdjacentHTML('beforeend',`<details><summary>OSM snapshot provenance</summary><p>Query version ${escapeHTML(result.version)} · <a href="/api/osm/snapshot/${result.sha256}" target="_blank">Raw OSM response ↗</a></p><pre>${escapeHTML(JSON.stringify({endpoint:result.endpoint,sha256:result.sha256,bbox:result.bbox,query:result.query},null,2))}</pre></details>`);
    }catch(error){if(selectedId===p.id)host.innerHTML=`<h3>OSM supporting evidence</h3><p>Unavailable: ${escapeHTML(error.message)}</p>`;}
  }
  update();
}
$('osm-context').checked=saved.get('osm')==='1';
$('osm-context').onchange=()=>{saveView();refreshOSM(true);};
map.on('moveend',()=>refreshOSM());
refreshOSM();
