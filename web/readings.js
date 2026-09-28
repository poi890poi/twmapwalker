'use strict';
function readingHistory(rows){return rows.length?rows.map(r=>`<li>${escapeHTML(r.value||'(cleared)')} · ${escapeHTML(r.status)} · ${escapeHTML(r.origin)}</li>`).join(''):'<li>No saved reading yet.</li>';}
function readingEditor(p){
  return `<section class="reading-editor"><h3>Reading and possible names</h3><p>Use <strong>?</strong> for each unreadable character, for example <strong>?ライ社</strong>. ロ is a normal character. Leave the reading empty if no character count is known.</p><label for="reading-value">Your reading</label><input id="reading-value" maxlength="80" value="${escapeHTML(p.reading||p.text||'')}" placeholder="e.g. ?ライ社"><div class="reading-actions"><label><input type="checkbox" id="reading-verified" ${p.reading_status==='confirmed'?'checked':''}> Complete reading verified from the map</label><button id="save-reading">Save reading</button></div><p id="reading-status" role="status">${p.reading_status?'Saved as '+escapeHTML(p.reading_status):'No independent reading saved.'}</p><p>Raw OCR: <strong>${escapeHTML(p.text||'(none)')}</strong> · retained unchanged.</p><div class="name-suggestions"><strong>Possible names</strong><p id="suggestion-status">Checking your search and nearby saved readings…</p><div id="name-suggestions"></div></div><details><summary>Reading history</summary><ul id="reading-history">${readingHistory(p.readings||[])}</ul></details></section>`;
}
function bindReadingEditor(p){
  let origin='manual';const input=$('reading-value'),verified=$('reading-verified');
  input.oninput=()=>{origin='manual';verified.checked=false;$('reading-status').textContent='Draft changes — not saved.';};
  $('save-reading').onclick=async()=>{
    const button=$('save-reading');button.disabled=true;
    try{
      const savedOrigin=origin;const result=await post(`/api/pois/${p.id}/reading`,{value:input.value,status:verified.checked?'confirmed':'tentative',origin:savedOrigin});
      if(selectedId!==p.id)return;
      input.value=result.value;p.reading=result.value;p.reading_status=result.status;p.display_text=result.value||p.text;
      p.readings.push({value:result.value,status:result.status,origin:savedOrigin});$('reading-history').innerHTML=readingHistory(p.readings);
      $('detail-title').textContent=label(p);$('reading-status').textContent=`Saved as ${result.status}. Raw OCR and finding review are unchanged.`;loadSuggestions();refresh();
    }catch(e){if(selectedId===p.id)$('reading-status').textContent=e.message;}finally{if(selectedId===p.id)button.disabled=false;}
  };
  function loadSuggestions(){
  const q=$('name-search').value;
  api(`/api/pois/${p.id}/suggestions?`+new URLSearchParams({q})).then(result=>{
    if(selectedId!==p.id)return;
    $('suggestion-status').textContent=(result.items.length?'Suggestions need your review. Selecting one only fills a draft.':'No supported name suggestion yet. Add known characters or search for a possible full name.')+(result.truncated?' Nearby-name search was limited.':'');
    const list=$('name-suggestions');list.replaceChildren();
    for(const item of result.items){
      const button=document.createElement('button');button.className='name-suggestion';
      const name=document.createElement('strong');name.textContent=item.name;const detail=document.createElement('small');detail.textContent=item.source+' · use as draft';button.append(name,detail);
      button.onclick=()=>{input.value=item.name;origin=item.origin;verified.checked=false;$('reading-status').textContent='Suggested reading in draft — not saved or verified.';input.focus();};list.append(button);
    }
  }).catch(e=>{if(selectedId===p.id)$('suggestion-status').textContent=e.message;});
  }
  loadSuggestions();
}
let nameSearchTimer;
$('name-search').oninput=()=>{requestId++;clearTimeout(nameSearchTimer);nameSearchTimer=setTimeout(()=>refresh(true),220);};
$('clear-search').onclick=()=>{clearTimeout(nameSearchTimer);$('name-search').value='';refresh(true);$('name-search').focus();};
