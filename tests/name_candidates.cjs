const assert=require('node:assert/strict'),fs=require('node:fs'),vm=require('node:vm');
const policy=require('../web/name-candidates.js');
const result={raw_readings:['山埔','埔山','山埔'],candidates:[{distance_m:314,name_match:{alias:'內茅埔山'},feature:{properties:{name:'內茅埔山',osm_type:'node',osm_id:23,tags:{old_name:'フルイ山'}}}}]};
const items=policy.items(result);
assert.deepEqual(items.map(i=>i.name),['山埔','埔山','內茅埔山','フルイ山']);
assert.equal(items[0].modern,false);assert.equal(items[2].modern,true);
assert.match(items[3].source,/old name/);
assert.deepEqual(items[3].osm,{type:'node',id:23,name:'內茅埔山'});
assert.equal(policy.items({raw_readings:['x'.repeat(81)],candidates:[]}).length,0);
const nearbyResult={...result,nearby_annotations:[{name:'內茅埔山',poi_id:42,source:'JM50K_1924_new',same_map:true,distance_m:18,classification:'poi',osm_type:'way',osm_id:24,osm_name:'Saved modern name'}]};
const nearbyItems=policy.items(nearbyResult);
assert.equal(nearbyItems[0].name,'內茅埔山');assert(nearbyItems[0].annotated);
assert.match(nearbyItems[0].source,/Saved POI #42.*same map.*18 m/);
assert.equal(nearbyItems.filter(r=>r.name==='內茅埔山').length,2); // Different linked objects remain selectable.
assert.deepEqual(nearbyItems[0].osm,{type:'way',id:24,name:'Saved modern name'});
const sameName=policy.items({raw_readings:['Same'],candidates:['node','relation'].map(osm_type=>({distance_m:1,feature:{properties:{name:'Same',osm_type,osm_id:1}}}))});
assert.equal(sameName.length,3);assert.equal(sameName[0].osm,undefined);
assert.equal(sameName[1].osm.type,'node');assert.equal(sameName[2].osm.type,'relation');
assert.equal(policy.items({candidates:[{distance_m:1,feature:{properties:{provider:'moi',record_id:3,name:'Gazetteer'}}} ]})[0].osm,null);
let fired,focused=false;
const input={value:'user draft',dispatchEvent:e=>{fired=e;},focus:()=>{focused=true;}};
policy.apply(input,'內茅埔山');
assert.equal(input.value,'內茅埔山');assert.equal(fired.type,'input');assert.equal(fired.bubbles,true);assert(focused);

function element(){return {children:[],append(...nodes){this.children.push(...nodes);},replaceChildren(){this.children=[];},textContent:''};}
const host=element(),status=element(),name={...input,value:'newer typed draft'};
const p={id:1},draft={p,osm:{id:88},classification:'noise'};
const context=vm.createContext({annotationDraft:draft,$:id=>({'candidate-names':host,'candidate-name-status':status,'annotation-name':name}[id]),document:{createElement:element},Event,
  selectAnnotationSuggestion:(item,selected)=>{assert.equal(selected,draft);policy.apply(name,item.name);if(item.classification)selected.classification=item.classification;if('osm' in item)selected.osm=item.osm;}});
vm.runInContext(fs.readFileSync(require.resolve('../web/name-candidates.js'),'utf8'),context);
context.p=p;context.result=result;
vm.runInContext('renderNameCandidates(p,result)',context);
assert.equal(name.value,'newer typed draft'); // Arrival never overwrites an edit.
const button=host.children[2];button.onclick();
assert.equal(name.value,'內茅埔山');assert.equal(draft.classification,'poi');assert.equal(draft.osm.id,23);
context.annotationDraft={p:{id:2}};name.value='other POI draft';button.onclick();
assert.equal(name.value,'other POI draft'); // Stale buttons cannot edit another POI.
console.log('Name candidates: provenance, deduplication, draft-only fill, input events and stale-detail safety passed.');

(async()=>{
  context.annotationDraft=draft;let finishNearby;context.api=()=>new Promise(yes=>{finishNearby=yes;});
  const local=vm.runInContext('loadNearbyAnnotatedNames(p)',context);
  name.value='typing while nearby loads';finishNearby({candidates:nearbyResult.nearby_annotations});await local;
  assert.equal(name.value,'typing while nearby loads');assert.match(host.children[0].children[1].textContent,/Saved POI/);
  host.children[0].onclick();assert.equal(name.value,'內茅埔山');assert.match(status.textContent,/proximity alone/);
  assert.equal(draft.osm.id,24);assert.equal(draft.classification,'poi');
  vm.runInContext('renderNameCandidates(p,result)',context); // Later external response preserves local names.
  assert.match(host.children[0].children[1].textContent,/Saved POI/);
  const late=vm.runInContext('loadNearbyAnnotatedNames(p)',context);context.annotationDraft={p:{id:2}};
  finishNearby({candidates:[]});await late;assert.equal(draft.nearbyNames.length,1);
  const readingHost=element(),readingStatus=element(),numberButton=element(),kanaButton=element();
  const elements={'reread-results':readingHost,'reread-status':readingStatus,'reread-numbers':numberButton,'reread-kana':kanaButton,'annotation-name':name};
  let resolve;const pending=new Promise(yes=>{resolve=yes;});
  context.$=id=>elements[id];context.api=()=>pending;context.annotationDraft=draft;
  vm.runInContext('bindReadingSuggestions(p)',context);
  const work=numberButton.onclick();assert(numberButton.disabled&&kanaButton.disabled);
  name.value='typed while waiting';resolve({readings:[{text:'1210',angle:0}]});await work;
  assert.equal(name.value,'typed while waiting');assert.equal(numberButton.disabled,false);
  readingHost.children[0].onclick();assert.equal(name.value,'1210');
  context.annotationDraft={p:{id:3}};name.value='another POI';readingHost.children[0].onclick();
  assert.equal(name.value,'another POI');
  context.annotationDraft=draft;let finish;context.api=()=>new Promise(yes=>{finish=yes;});
  const stale=kanaButton.onclick();context.annotationDraft={p:{id:4}};
  finish({readings:[{text:'ウ',angle:0}]});await stale;assert.equal(readingHost.children.length,0);
  context.annotationDraft=draft;context.api=async()=>{throw Error('source unavailable');};
  await numberButton.onclick();assert.equal(numberButton.disabled,false);assert.match(readingStatus.textContent,/source unavailable/);
  console.log('Rereading: late results, draft-only fill, stale POI, failure and retry passed.');
})().catch(error=>{console.error(error);process.exitCode=1;});
