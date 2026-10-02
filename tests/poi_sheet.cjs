const assert=require('node:assert/strict');
const {attach}=require('../web/poi-sheet.js');
const listeners={},attributes={},classes=new Set(),styles={},caption={};
let captured=null,resizes=0,focused=false;
const draft={value:'Unsaved mountain name'},doc={activeElement:draft};
const panel={open:true,dataset:{},ownerDocument:doc,contains:el=>el===draft,
  classList:{add:x=>classes.add(x),remove:x=>classes.delete(x)},
  getBoundingClientRect:()=>({height:styles['--poi-sheet-height']==='100%'?700:styles['--poi-sheet-height']==='44px'?44:350})};
const handle={addEventListener:(type,fn)=>listeners[type]=fn,setAttribute:(k,v)=>attributes[k]=v,
  querySelector:()=>caption,focus:()=>{focused=true;},setPointerCapture:id=>{captured=id;},
  hasPointerCapture:id=>captured===id,releasePointerCapture:()=>{captured=null;}};
const media={matches:true,addEventListener:(type,fn)=>{media.change=fn;}};
const sheet=attach({panel,handle,container:{style:{setProperty:(k,v)=>styles[k]=v},getBoundingClientRect:()=>({height:700})},media,onResize:()=>resizes++});
const event=(type,extra={})=>listeners[type]({pointerId:1,isPrimary:true,button:0,clientX:100,clientY:400,preventDefault(){},...extra});
function swipe(dy,dx=0){event('pointerdown');event('pointermove',{clientY:400+dy,clientX:100+dx});event('pointerup',{clientY:400+dy,clientX:100+dx});event('click',{detail:1});}
assert.equal(sheet.state,'half');swipe(-100);assert.equal(sheet.state,'full');
swipe(100);assert.equal(sheet.state,'half');swipe(100);assert.equal(sheet.state,'hidden');
assert.equal(attributes['aria-expanded'],'false');assert.equal(focused,true);
assert.equal(draft.value,'Unsaved mountain name');assert.equal(panel.open,true);
swipe(-100);assert.equal(sheet.state,'half');
swipe(20,100);assert.equal(sheet.state,'half','Horizontal swipes must not become clicks');
event('pointerdown');event('pointermove',{clientY:250});event('pointercancel');
assert.equal(sheet.state,'half');assert.equal(styles['--poi-sheet-height'],'50%');
assert.equal(classes.has('sheet-dragging'),false);
event('keydown',{key:'ArrowUp'});assert.equal(sheet.state,'full');
event('keydown',{key:'End'});assert.equal(sheet.state,'hidden');
event('click',{detail:0});assert.equal(sheet.state,'half','Keyboard activation restores the panel');
swipe(500);assert.equal(sheet.state,'hidden');sheet.reveal();assert.equal(sheet.state,'half');
media.matches=false;media.change();swipe(-100);assert.equal(sheet.state,'half','Desktop ignores swipe gestures');
assert(resizes>0);assert.equal(draft.value,'Unsaved mountain name');
console.log('POI sheet: full/half/hidden swipes, horizontal/cancel handling, keyboard access, draft retention and desktop boundary passed.');
