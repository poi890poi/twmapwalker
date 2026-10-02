'use strict';
let multiEvidenceTimer;
const supportLabels={'name-supported':'Name overlap — inspect the match',ambiguous:'Several possible matches',
  'elevation-compatible':'Height-compatible — contour or spot unresolved',unknown:'Identity unresolved','context-only':'Nearby context only'};

function supportingEvidenceHTML(result){
  let html=`<p><strong>${escapeHTML(supportLabels[result.state]||'Identity unresolved')}</strong></p><p>Automatic map readings: <bdi>${escapeHTML(result.raw_readings.join(' / ')||'(unread)')}</bdi>. Search area: ${result.radius_m} m.</p>`;
  const coverage=result.coverage,osm=coverage.osm||{},gaz=coverage.gazetteer||{},terrain=coverage.terrain||{};
  if(osm.state!=='complete')html+='<p>OSM coverage is incomplete or refreshing. Missing matches are undecided.</p>';
  if(osm.truncated)html+='<p>OSM input was limited to the nearest 200 features; farther matches may be absent.</p>';
  if(gaz.state!=='available')html+='<p>Official place-name data is unavailable.</p>';
  if(terrain.state!=='available')html+='<p>Terrain evidence is unavailable.</p>';
  if(result.numeric_note)html+=`<p>${escapeHTML(result.numeric_note)}</p>`;
  html+=`<p>${escapeHTML(result.note)}</p><div class="osm-evidence-list">`;
  for(const candidate of result.candidates){
    const f=candidate.feature.properties;
    // Source URLs are created by the server's OSM/gazetteer normalizers.
    const provider=f.provider==='moi'?'MOI place-name record':'OpenStreetMap';
    html+=`<details><summary><strong>${escapeHTML(f.name||osmSummary(f))}</strong><span>~${candidate.distance_m} m · ${escapeHTML(supportLabels[candidate.support])}</span></summary><p><a href="${escapeHTML(f.url)}" target="_blank" rel="noopener">${provider} ↗</a></p>`;
    for(const e of candidate.evidence){
      if(e.channel==='name')html+=`<p>Map “${escapeHTML(e.reading)}” ↔ name/alias “${escapeHTML(e.alias)}” (${escapeHTML(e.reason)}).</p>`;
      if(e.channel==='type')html+=`<p>Character suggests ${escapeHTML(e.value)}; this cannot identify the place.</p>`;
      if(e.channel==='elevation')html+=`<p>${e.comparisons.map(c=>`${c.reading_m} ↔ modern ${c.modern_m} m (difference ${c.difference_m} m)`).join('; ')}. Assumes historical metres.</p>`;
      if(e.channel==='terrain')html+=e.state==='available'?`<p>Native ${e.native_resolution_m} m DTM: ${e.elevation_m} m at the modern coordinate; ${e.below_local_max_m} m below the highest grid point within ${e.local_radius_m} m.${e.peak_like?' Near a local terrain high.':''}${e.modern_height_compatible===false?' Modern stated height and DTM differ; inspect both.':''}</p>`:`<p>Terrain at this location: ${escapeHTML(e.state)}. This supplies no negative evidence.</p>`;
    }
    html+='</details>';
  }
  html+='</div>';
  if(!result.candidates.length)html+='<p>No matching context in the available sources. This does not rule out a historical POI.</p>';
  html+=`<details><summary>Sources and coverage</summary><p>© OpenStreetMap contributors · ODbL 1.0. Taiwan Ministry of the Interior place names and DTM · Government Data Open License 1.0.</p><pre>${escapeHTML(JSON.stringify(coverage,null,2))}</pre></details>`;
  return html;
}

async function loadMultiEvidence(p){
  clearTimeout(multiEvidenceTimer);
  const host=$('multi-evidence');if(!host)return;
  host.textContent='Comparing automatic readings, names and terrain…';
  async function update(){
    if(selectedId!==p.id||!$('detail').open||$('multi-evidence')!==host)return;
    try{
      const result=await api(`/api/pois/${p.id}/supporting-evidence`);
      if(selectedId!==p.id||!$('detail').open||$('multi-evidence')!==host)return;
      host.innerHTML=supportingEvidenceHTML(result);
      renderNameCandidates(p,result);
      if(['pending','running'].includes(result.coverage.osm?.state))multiEvidenceTimer=setTimeout(update,5000);
    }catch(error){if(selectedId===p.id&&$('multi-evidence')===host){
      host.textContent='Supporting evidence unavailable: '+error.message;
      renderNameCandidates(p,{raw_readings:[p.text,...(p.details?.reading_candidates||[]).map(r=>r.text)],candidates:[]});
    }}
  }
  update();
}
