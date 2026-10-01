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
  function contextBounds(b){
    // Keep surrounding terrain visible even for a single character or point.
    const latitude=(b[1]+b[3])/2;
    const dy=Math.max(250/111320,(b[3]-b[1])*.25);
    const dx=Math.max(250/(111320*Math.cos(latitude*Math.PI/180)),(b[2]-b[0])*.25);
    return [b[0]-dx,b[1]-dy,b[2]+dx,b[3]+dy];
  }
  const api={bounds,contextBounds};
  if(typeof module!=='undefined')module.exports=api;
  else root.MapwalkerPOI=api;
})(typeof window!=='undefined'?window:globalThis);
