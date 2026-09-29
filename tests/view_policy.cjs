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
