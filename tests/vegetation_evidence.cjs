const assert=require('node:assert/strict'),fs=require('node:fs'),vm=require('node:vm');
const elements=new Map();
function el(){return {textContent:'',disabled:false,style:{},children:[],append(x){this.children.push(x);},replaceChildren(){this.children=[];}};}
function get(id){if(!elements.has(id))elements.set(id,el());return elements.get(id);}
const p={id:1,kind:'symbol',z:16},draft={p,osm:{type:'node',id:9},name:'Keep',note:'Keep notes'};
draft.members=new Map([[1,p]]);
let chosen=[],requests=[];
const ctx=vm.createContext({annotationDraft:draft,$:get,document:{createElement:()=>el()},setAnnotationClass:v=>chosen.push(v),
 api:url=>new Promise((resolve,reject)=>requests.push({url,resolve,reject}))});
vm.runInContext(fs.readFileSync(require.resolve('../web/vegetation.js'),'utf8'),ctx);
(async()=>{
 ctx.bindVegetationEvidence(p);const button=get('check-vegetation');let pending=button.onclick();
 assert(button.disabled);requests.shift().resolve({status:'candidate',matches:[{}],preview:'data:image/png;base64,x'});await pending;
 assert.deepEqual(chosen,[]);assert(!button.disabled);
 const use=get('vegetation-result').children.at(-1);use.onclick();assert.deepEqual(chosen,['other']);
 assert.equal(draft.osm.id,9);assert.equal(draft.name,'Keep');assert.equal(draft.note,'Keep notes');
 pending=button.onclick();requests.shift().resolve({status:'numeric-context',matches:[]});await pending;
 assert.equal(get('vegetation-result').children.length,0);assert.match(get('vegetation-status').textContent,/numeric/);
 pending=button.onclick();requests.shift().reject(new Error('input hash mismatch'));await pending;
 assert.match(get('vegetation-status').textContent,/unavailable/);assert(!button.disabled);
 pending=button.onclick();draft.members.set(2,{id:2});requests.shift().resolve({status:'candidate',matches:[{}]});await pending;
 assert.equal(get('vegetation-result').children.length,0);assert.match(get('vegetation-status').textContent,/grouped/);
 use.onclick();assert.deepEqual(chosen,['other']);await button.onclick();assert.equal(requests.length,0);
 draft.members.delete(2);
 pending=button.onclick();ctx.annotationDraft={p:{id:2}};get('vegetation-status').textContent='New editor';
 requests.shift().resolve({status:'candidate',matches:[{}],preview:'data:image/png;base64,old'});await pending;
 assert.equal(get('vegetation-status').textContent,'New editor');use.onclick();assert.deepEqual(chosen,['other']);
 ctx.annotationDraft=draft;
 p.vegetation_evidence={status:'candidate',matches:[{}],preview:'data:image/png;base64,cached',profile:'current',input_key:'input'};
 let writes=[];ctx.post=async(url,body)=>{writes.push({url,body});};ctx.refresh=()=>{};
 await ctx.bindVegetationEvidence(p);
 assert.equal(requests.length,0);assert.equal(get('vegetation-section').open,true);
 assert.equal(get('vegetation-notice').hidden,false);assert.deepEqual(chosen,['other']);
 await get('vegetation-result').children.at(-1).onclick();
 assert.equal(writes.length,1);assert.equal(writes[0].body.outcome,'dismiss');
 assert.equal(writes[0].body.items[0].id,1);assert.equal(get('vegetation-notice').hidden,true);
 assert.deepEqual(chosen,['other']);assert.match(get('vegetation-status').textContent,/Annotation unchanged/);
 p.vegetation_evidence={status:'numeric-context'};
 await ctx.bindVegetationEvidence(p);assert.equal(requests.length,0);assert.equal(get('vegetation-notice').hidden,true);
 p.vegetation_evidence={status:'unchecked'};
 pending=ctx.bindVegetationEvidence(p);assert.equal(requests.length,1);
 requests.shift().resolve({status:'no-match'});await pending;assert.equal(get('vegetation-result').children.length,0);
 p.vegetation_evidence=null;await ctx.bindVegetationEvidence(p);assert.equal(requests.length,0);
 p.vegetation_evidence={status:'unchecked'};draft.members.set(2,{id:2});
 await ctx.bindVegetationEvidence(p);assert.equal(requests.length,0);
 console.log('Vegetation evidence: automatic cache/check, dismissal, numeric veto, draft-only choice, grouped/stale responses and field preservation pass.');
})().catch(e=>{console.error(e);process.exitCode=1;});
