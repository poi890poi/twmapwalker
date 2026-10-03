'use strict';
function bindVegetationEvidence(p){
  const draft=annotationDraft,button=$('check-vegetation'),host=$('vegetation-result'),status=$('vegetation-status'),section=$('vegetation-section'),notice=$('vegetation-notice');
  if(!button||!host||!status)return;
  const single=()=>draft?.members?.size===1&&draft.members.has(p.id);
  const grouped=()=>{host.replaceChildren();if(notice)notice.hidden=true;status.textContent='This check applies to one map fragment. Review grouped labels together before changing their type.';};
  button.disabled=p.kind==='trail'||p.z!==16;
  if(button.disabled)status.textContent='This check is available for text and symbol findings at the original map scale.';
  const check=async(cached)=>{
    if(annotationDraft!==draft)return;
    if(!single()){grouped();return;}
    if(notice)notice.hidden=true;
    button.disabled=true;host.replaceChildren();status.textContent='Checking the original symbol shape and size…';
    try{
      const result=cached||await api(`/api/pois/${p.id}/vegetation-evidence`);
      if(annotationDraft!==draft||$('vegetation-result')!==host)return;
      if(!single()){grouped();return;}
      if(result.status!=='candidate'||!result.matches?.length){
        status.textContent=result.status==='numeric-context'
          ?'A possible numeric label overlaps this mark. No vegetation suggestion; compare the complete number.'
          :result.status==='no-match'
          ?'No strong vegetation pattern found. This does not establish that the finding is a POI.'
          :'This finding is outside the supported symbol scale.';return;
      }
      if(section)section.open=true;
      if(notice){
        notice.hidden=false;notice.textContent='Possible vegetation · Review suggestion';
        notice.onclick=()=>{showDetailTab('annotation');section?.scrollIntoView({block:'nearest'});};
      }
      status.textContent='Possible vegetation symbol: a small ring with a downward stem. Compare the map before choosing Other.';
      if(result.preview){
        const image=document.createElement('img');image.src=result.preview;image.alt='Original map crop: orange detection box and green matching symbol';
        image.style.maxWidth='100%';image.style.height='auto';host.append(image);
      }
      const caption=document.createElement('p');caption.className='annotation-help';caption.textContent='Orange: detection. Green: matching shape. This check can miss vegetation or confuse another symbol.';host.append(caption);
      const use=document.createElement('button');use.type='button';use.textContent='Use Other — not saved';
      use.onclick=()=>{
        if(annotationDraft!==draft||$('vegetation-result')!==host)return;
        if(!single()){grouped();return;}
        setAnnotationClass('other');status.textContent='Other selected as a draft. Save annotation when ready.';
      };host.append(use);
      if(result.profile&&result.input_key){
        const dismiss=document.createElement('button');dismiss.type='button';dismiss.textContent='Dismiss suggestion';
        dismiss.onclick=async()=>{
          if(annotationDraft!==draft||$('vegetation-result')!==host)return;
          dismiss.disabled=true;
          try{
            await post('/api/vegetation-review/decisions',{profile:result.profile,items:[{id:p.id,input_key:result.input_key}],outcome:'dismiss'});
            if(annotationDraft!==draft||$('vegetation-result')!==host)return;
            host.replaceChildren();if(notice)notice.hidden=true;
            status.textContent='Suggestion dismissed. Annotation unchanged.';refresh();
          }catch(error){if(annotationDraft===draft&&$('vegetation-result')===host){status.textContent=error.message;dismiss.disabled=false;}}
        };host.append(dismiss);
      }
    }catch(error){
      if(annotationDraft===draft&&$('vegetation-result')===host)status.textContent='Symbol check unavailable: '+error.message;
    }finally{
      if(annotationDraft===draft&&$('vegetation-result')===host)button.disabled=false;
    }
  };
  button.onclick=()=>check();
  // Cached negatives cost no OCR. Unchecked, unreviewed fragments run on opening.
  // Saved annotations and dismissed suggestions have no automatic advice.
  if(!button.disabled&&single()&&p.vegetation_evidence)
    return check(p.vegetation_evidence.status==='unchecked'?null:p.vegetation_evidence);
}
