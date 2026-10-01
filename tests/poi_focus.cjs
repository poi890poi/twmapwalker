const assert=require('node:assert/strict');
const {bounds}=require('../web/poi-focus.js');
// A text detection has point bounds in storage, but its actual ink covers a box.
const p={lon:0,lat:0,x:1,y:1,z:1,box:[0,0,128,128],west:0,east:0,south:0,north:0};
assert.deepEqual(bounds(p),[0,-66.51326044311186,90,0]);
// Halo detections can extend beyond the source tile; do not clamp their box.
assert.equal(bounds({...p,box:[-64,-64,320,320]})[0],-45);
assert.equal(bounds({...p,box:[-64,-64,320,320]})[2],225);
// Stored path geometry and legacy findings still contribute their complete extent.
assert.deepEqual(bounds({lon:121,lat:24,west:120,south:23,east:122,north:25}),[120,23,122,25]);
assert.deepEqual(bounds({lon:121,lat:24}),[121,24,121,24]);
console.log('POI focus: text box, halo, path and legacy bounds passed.');
