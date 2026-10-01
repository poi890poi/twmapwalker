const assert=require('node:assert/strict');
const {bounds,contextBounds}=require('../web/poi-focus.js');
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
// Even point detections get 250 m of surrounding terrain on every side.
const context=contextBounds([121,24,121,24]);
assert.ok(Math.abs((context[2]-121)*111320*Math.cos(24*Math.PI/180)-250)<1e-6);
assert.ok(Math.abs((context[3]-24)*111320-250)<1e-6);
assert.ok(context[0]<121&&context[1]<24);
// A wide fragment group keeps its full extent plus proportional context.
const group=[120.99,23.99,121.01,24.01],wide=contextBounds(group);
assert.ok(wide[0]<=120.985&&wide[1]<=23.985&&wide[2]>=121.015&&wide[3]>=24.015);
console.log('POI context: minimum ground distance and complete group extent passed.');
