/* Selection geometry is separate from detector/display point bounds. */
(function(root){
  'use strict';
  function bounds(p){
    const points=[[p.lon,p.lat]];
    if(Array.isArray(p.box)&&p.box.length===4&&p.box.every(Number.isFinite)&&[p.x,p.y,p.z].every(Number.isFinite)){
      for(const [px,py] of [[p.box[0],p.box[1]],[p.box[2],p.box[3]]]){
        const x=(p.x+px/256)/2**p.z,y=(p.y+py/256)/2**p.z;
        points.push([x*360-180,Math.atan(Math.sinh(Math.PI*(1-2*y)))*180/Math.PI]);
      }
    }
    if([p.west,p.south,p.east,p.north].every(Number.isFinite))points.push([p.west,p.south],[p.east,p.north]);
    const valid=points.filter(p=>p.every(Number.isFinite));
    return [Math.min(...valid.map(p=>p[0])),Math.min(...valid.map(p=>p[1])),Math.max(...valid.map(p=>p[0])),Math.max(...valid.map(p=>p[1]))];
  }
  const api={bounds};
  if(typeof module!=='undefined')module.exports=api;
  else root.MapwalkerPOI=api;
})(typeof window!=='undefined'?window:globalThis);
