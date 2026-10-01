const assert = require('node:assert/strict');
const view = require('../web/view-policy.js');

// The exact value from the phone screenshot must never enter an integer request.
assert.equal(view.zoom(15.218098151851985), 15);
assert.equal(view.zoom(15.5), 16);
for (const input of [4,5,15,19,20,NaN,Infinity]) {
  const value = view.zoom(input);
  assert(Number.isInteger(value) && value >= 5 && value <= 19);
}
const error = view.error([{type:'int_parsing',loc:['query','zoom'],input:'15.218098151851985'}],422);
assert(error.length < 100);
assert(!error.includes('int_parsing') && !error.includes('query') && !error.includes('['));
assert(!view.error({internal:'trace'},500).includes('trace'));
assert.equal(view.error('Zoom in to select a smaller area.',400),'Zoom in to select a smaller area.');
console.log('Zoom normalization and readable-error regressions passed.');

const pending={state:'queued',total:70,complete:0,not_queued:0,working_elsewhere:true,current:null,findings:{candidates:0,excluded:0},checks:{total:420,complete:0,pending:420,running:0,failed:0,percent:0}};
const empty={total:0,display:{available:0}};
assert(view.discovery(pending).title.includes('Queued'));
assert(view.discovery(pending).current.includes('Other areas'));
assert(!view.empty(pending,empty).message.includes('Search complete'));
const done={...pending,state:'complete',complete:70,working_elsewhere:false,checks:{...pending.checks,complete:420,pending:0,percent:100}};
assert(view.discovery(done).title.includes('Search complete'));
assert(view.empty(done,empty).message.includes('may still have been missed'));
assert.equal(view.empty(done,{total:0,display:{available:8}}).action,'all');
assert.equal(view.empty({...done,findings:{candidates:5,excluded:0}},empty,true).action,'filters');
assert.equal(view.empty({...done,findings:{candidates:0,excluded:7}},empty).action,'excluded');
assert.equal(view.empty({...done,state:'failed'},empty).action,'jobs');
assert.equal(view.empty(pending,{total:2,display:{available:2}}).message,'');
console.log('Area progress, incomplete work, display/filter hiding and completed-empty regressions passed.');

assert(view.empty({...pending,findings:{candidates:5,excluded:0}},empty).message.includes('updating'));
const blank={...done,blank_tiles:70,blank_checks:420};
assert.equal(view.discovery(blank).title,'Blank map area ignored');
assert(view.discovery(blank).detail.includes('70 blank ignored'));
assert(view.empty(blank,empty).message.includes('No detector work'));
assert(view.discovery({...done,blank_tiles:3}).detail.includes('3 blank ignored'));
assert.equal(view.empty({...done,findings:{candidates:5,excluded:0}},{...empty,visibility:'visible'}).action,'hidden');
assert(view.empty(done,{...empty,visibility:'hidden'}).message.includes('No hidden POIs'));
