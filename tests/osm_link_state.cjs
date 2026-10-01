// Exercise the actual UI renderer without network or a browser dependency.
const assert=require('node:assert/strict'),fs=require('node:fs'),vm=require('node:vm');
class Element {
  constructor(tag='div'){this.tagName=tag;this.children=[];this.dataset={};}
  append(...children){this.children.push(...children);}
  replaceChildren(...children){this.children=children;}
  set textContent(value){this.children=[value];}
  get textContent(){return this.children.map(c=>typeof c==='string'?c:c.textContent).join('');}
}
const ids=new Map(),get=id=>{if(!ids.has(id))ids.set(id,new Element());return ids.get(id);};
const nodeChoice=new Element('button');nodeChoice.dataset.osmChoice='node/123';
const relationChoice=new Element('button');relationChoice.dataset.osmChoice='relation/123';
const context=vm.createContext({$:get,L:{layerGroup:()=>({clearLayers(){}})},map:{on(){}},detailSaved:new Map(),
  document:{createElement:tag=>new Element(tag),querySelectorAll:()=>[nodeChoice,relationChoice]}});
vm.runInContext(fs.readFileSync(require.resolve('../web/annotations.js'),'utf8'),context);
const run=code=>vm.runInContext(code,context),summary=()=>get('detail-osm-status').textContent;
const button=name=>get('osm-selected').children.find(c=>c.tagName==='button'&&c.textContent===name);
run('annotationDraft={p:{annotation:{}},osm:null};renderOSMSelection()');
assert.equal(summary(),'OSM · No saved link');
run("annotationDraft.osm={type:'node',id:123,name:'同名地點'};renderOSMSelection()");
assert(summary().includes('No saved link')&&summary().includes('Selected — not saved: 同名地點 · node 123'));
assert.equal(nodeChoice.textContent,'Selected — not saved');
assert.equal(nodeChoice.disabled,true);
assert.equal(run('annotationDraft.p.annotation.osm_id'),undefined); // Selection does not save.
// Only a successful save response updates p.annotation in the application.
run("annotationDraft.p.annotation={osm_type:'node',osm_id:123,osm_name:'同名地點'};renderOSMSelection()");
assert.equal(summary(),'OSM · Saved link: 同名地點 · node 123');
assert.equal(get('detail-osm-status').children[0].children[1].href,'https://www.openstreetmap.org/node/123');
assert.equal(nodeChoice.textContent,'Saved link');
run("annotationDraft.osm={type:'relation',id:123,name:'同名地點'};renderOSMSelection()");
assert(summary().includes('Saved link: 同名地點 · node 123'));
assert(summary().includes('Selected — not saved: 同名地點 · relation 123')); // Same ID/name, different type.
assert.equal(nodeChoice.disabled,false);
assert.equal(relationChoice.disabled,true);
// A failed save leaves the persisted annotation unchanged, hence stays pending.
run('renderOSMSelection()');
assert(summary().includes('Selected — not saved'));
button('Undo link change').onclick();
assert.equal(summary(),'OSM · Saved link: 同名地點 · node 123');
button('Remove link').onclick();
assert(summary().includes('Saved link: 同名地點 · node 123')&&summary().includes('Removal — not saved'));
run("annotationDraft.p.annotation={osm_type:'',osm_id:null,osm_name:''};renderOSMSelection()");
assert.equal(summary(),'OSM · No saved link');
// An earlier save finishing must not mark a newer selection as saved.
run("annotationDraft.p.annotation={osm_type:'node',osm_id:123,osm_name:'同名地點'};annotationDraft.osm={type:'way',id:456,name:''};renderOSMSelection()");
assert(summary().includes('Saved link: 同名地點 · node 123')&&summary().includes('Selected — not saved: way 456'));
console.log('OSM link UI: empty, selection, save, replacement, undo, removal and pending newer edits passed.');
