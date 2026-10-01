'use strict';
function annotationHistory(rows){return rows.length?rows.slice().reverse().map(r=>`<li><bdi>${escapeHTML(r.payload.ground_truth||'(no name)')}</bdi> · ${escapeHTML(r.payload.classification||'unclassified')}<br>${escapeHTML(r.payload.note||'')}</li>`).join(''):'<li>No saved annotations.</li>';}
function annotationEditor(p){
  const a=p.annotation||{};
  return `<section class="annotation-editor"><h3>Ground truth</h3>
  <p>Enter the name in normal reading order. Use <strong>?</strong> for unreadable characters.</p><details class="reading-help"><summary>How to enter right-to-left text</summary><p>For historical Chinese/Japanese printed right-to-left, enter the correctly read name and record the map direction below. For Arabic/Hebrew, type normally; display direction is automatic.</p></details>
  <label>Ground-truth name <input id="annotation-name" dir="auto" maxlength="200" value="${escapeHTML(a.ground_truth||'')}"></label>
  <label>Classification <select id="annotation-class"><option value="unclassified">Unclassified</option><option value="poi">POI</option><option value="noise">Noise / false detection</option></select></label>
  <label>Writing direction on the original map <select id="annotation-direction"><option value="unknown">Unknown</option><option value="ltr">Left to right</option><option value="rtl">Right to left</option><option value="vertical">Vertical</option></select></label>
  <details class="evidence-section"><summary>Group fragmented detections</summary><p>Fragment group: <span id="annotation-group">${escapeHTML(a.group_id||'None')}</span>. Grouping keeps each original detection and its evidence.</p>
  <label>Group with POI IDs (comma separated) <input id="annotation-fragments" placeholder="e.g. 123, 124" inputmode="numeric"></label>
  </details><details class="evidence-section" ${a.osm_type?'open':''}><summary>Associate an OpenStreetMap object</summary><p>Enter the type and ID from the object’s OpenStreetMap page.</p><label>OSM object type <select id="annotation-osm-type"><option value="">None</option><option value="node">Node</option><option value="way">Way</option><option value="relation">Relation</option></select></label>
  <label>OSM object ID <input id="annotation-osm-id" type="number" min="1" step="1" value="${a.osm_id||''}"></label>
  </details><label>Evidence / notes <textarea id="annotation-note" dir="auto" maxlength="2000">${escapeHTML(a.note||'')}</textarea></label>
  <div class="annotation-save"><button id="save-annotation">Save annotation</button><p id="annotation-status" role="status">${p.annotations?.length?'Saved annotation available.':'No annotation saved.'}</p></div>
  <details class="evidence-section"><summary>Annotation history</summary><ul id="annotation-history">${annotationHistory(p.annotations||[])}</ul></details></section>`;
}
function bindAnnotationEditor(p){
  const a=p.annotation||{};
  $('annotation-class').value=a.classification||'unclassified';$('annotation-direction').value=a.map_direction||'unknown';$('annotation-osm-type').value=a.osm_type||'';
  $('save-annotation').onclick=async()=>{
    const button=$('save-annotation');button.disabled=true;
    const values=detailValues('annotation-editor');
    try{
      const raw=$('annotation-fragments').value.trim();
      const ids=raw?raw.split(',').map(v=>Number(v.trim())):[];
      if(ids.some(v=>!Number.isSafeInteger(v)||v<=0))throw Error('Use positive POI IDs separated by commas.');
      const result=await post(`/api/pois/${p.id}/annotation`,{ground_truth:$('annotation-name').value,classification:$('annotation-class').value,map_direction:$('annotation-direction').value,fragment_ids:ids,osm_type:$('annotation-osm-type').value,osm_id:$('annotation-osm-id').value?Number($('annotation-osm-id').value):null,note:$('annotation-note').value});
      if(!isCurrentDetail(p))return;
      p.annotation=result.annotation;(p.annotations||=[]).push({payload:result.annotation});
      $('annotation-group').textContent=result.annotation.group_id||'None';
      const unchanged=detailValues('annotation-editor')===values;
      if(unchanged){$('annotation-fragments').value='';markDetailSaved('annotation-editor');}
      else markDetailSaved('annotation-editor',values);
      $('annotation-history').innerHTML=annotationHistory(p.annotations);
      $('annotation-status').textContent=unchanged?'Annotation saved.':'Saved earlier changes. Your newer edits are still unsaved.';
    }catch(e){if(isCurrentDetail(p))$('annotation-status').textContent=e.message;}
    finally{if(isCurrentDetail(p))button.disabled=false;}
  };
}
