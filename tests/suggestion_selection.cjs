// Exercise actual editor selection and save payload, with no production writes.
const assert=require('node:assert/strict'),fs=require('node:fs'),vm=require('node:vm');
const fields=new Map(),get=id=>{
  if(!fields.has(id))fields.set(id,{value:'',textContent:'',open:false,dispatchEvent(){},focus(){}});
  return fields.get(id);
};
const classes=['poi','other','unclassified','noise'].map(value=>({dataset:{class:value},setAttribute(k,v){this[k]=v;}}));
let payload,dirty=0,linkRenders=0;
const p={id:1,text:'Fragment',box:[0,0,10,10],annotation:{ground_truth:'Old',classification:'noise',osm_type:'way',osm_id:90,osm_name:'Previous'}};
const ctx=vm.createContext({$:get,p,Event,L:{layerGroup:()=>({clearLayers(){}})},map:{on(){}},
  document:{querySelectorAll:()=>classes,querySelector:()=>({})},
  detailValues:()=>JSON.stringify([get('annotation-name').value,get('annotation-class').value,get('annotation-osm').value]),
  markDetailSaved(){},isCurrentDetail:()=>true,label:p=>p.reading,closeDetail:()=>true,toast(){},refresh(){},
  post:async(url,body)=>{payload=body;return {annotation:body,hidden:false};}});
vm.runInContext(fs.readFileSync(require.resolve('../web/annotations.js'),'utf8'),ctx);
vm.runInContext(fs.readFileSync(require.resolve('../web/name-candidates.js'),'utf8'),ctx);
ctx.changed=()=>dirty++;ctx.rendered=()=>linkRenders++;
const run=code=>vm.runInContext(code,ctx);
run(`annotationChanged=changed;renderFragmentMembers=()=>{};renderVisibility=()=>{};
scheduleDirection=()=>{};setFragmentPicking=()=>{};showDirection=()=>{};annotationHistory=()=>'';
renderOSMSelection=()=>{$('annotation-osm').value=JSON.stringify(annotationDraft.osm);rendered();annotationChanged();};
bindAnnotationEditor(p);`);
get('annotation-note').value='Keep my notes';get('annotation-direction').value='vertical';
run("selectAnnotationSuggestion({name:'Saved historical name',classification:'poi',osm:{type:'relation',id:123,name:'Modern counterpart'}})");
assert.equal(get('annotation-name').value,'Saved historical name');
assert.equal(get('annotation-class').value,'poi');assert.equal(classes[0]['aria-pressed'],'true');
assert.equal(classes[3]['aria-pressed'],'false');
assert.deepEqual(JSON.parse(get('annotation-osm').value),{type:'relation',id:123,name:'Modern counterpart'});
assert.equal(p.annotation.ground_truth,'Old');assert.equal(p.annotation.osm_id,90); // Still draft.
assert(dirty>0&&linkRenders>0);
// A stale selection cannot touch a different editor.
run("selectAnnotationSuggestion({name:'Stale',classification:'noise',osm:null},{p:{id:2}})");
assert.equal(get('annotation-name').value,'Saved historical name');
(async()=>{
  await get('save-annotation').onclick();
  assert.equal(payload.ground_truth,'Saved historical name');assert.equal(payload.classification,'poi');
  assert.equal(payload.osm_type,'relation');assert.equal(payload.osm_id,123);assert.equal(payload.osm_name,'Modern counterpart');
  assert.equal(payload.note,'Keep my notes');assert.equal(payload.map_direction,'vertical');assert.deepEqual(Array.from(payload.member_ids),[1]);
  run("selectAnnotationSuggestion({name:'Unlinked saved POI',classification:'poi',osm:null})");
  assert.equal(get('annotation-osm').value,'null');
  await get('save-annotation').onclick();assert.equal(payload.osm_type,'');assert.equal(payload.osm_id,null);
  run("selectAnnotationSuggestion({name:'Linked',classification:'poi',osm:{type:'node',id:7,name:'Linked'}})");
  run("selectAnnotationSuggestion({name:'OCR correction'})");
  assert.equal(get('annotation-name').value,'OCR correction');assert.equal(get('annotation-class').value,'poi');
  assert.equal(JSON.parse(get('annotation-osm').value).id,7); // Reading-only corrections preserve association.
  console.log('Suggested POI: complete draft, save payload, unlinked replacement, OCR-only edit, stale draft and unrelated fields passed.');
})().catch(e=>{console.error(e);process.exitCode=1;});
