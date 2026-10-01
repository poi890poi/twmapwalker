// Exercise the actual save handler, including edits made while a save is pending.
const assert=require('node:assert/strict'),fs=require('node:fs'),vm=require('node:vm');
async function scenario(outcome){
  const elements=new Map(),get=id=>{
    if(!elements.has(id))elements.set(id,{value:'',textContent:'',open:false});
    return elements.get(id);
  };
  let values='submitted',saved,resolve,reject,closed=false,refreshed=false;
  const request=new Promise((yes,no)=>{resolve=yes;reject=no;});
  const p={id:1,text:'社',box:[0,0,10,10],annotation:{}};
  const context=vm.createContext({$:get,p,L:{layerGroup:()=>({})},map:{on(){}},
    document:{querySelectorAll:()=>[],querySelector:()=>({})},
    detailValues:()=>values,markDetailSaved:(section,value)=>{saved=value;},
    isCurrentDetail:()=>!closed,post:()=>request,label:p=>p.reading,
    closeDetail:showList=>{assert.equal(showList,false);assert.equal(saved,values);closed=true;return true;},
    toast:message=>assert.equal(message,'Annotation saved.'),refresh:()=>{refreshed=true;}});
  vm.runInContext(fs.readFileSync(require.resolve('../web/annotations.js'),'utf8'),context);
  vm.runInContext(`
    annotationChanged=()=>{};renderFragmentMembers=()=>{};renderOSMSelection=()=>{};
    renderVisibility=()=>{};scheduleDirection=()=>{};setFragmentPicking=()=>{};
    showDirection=()=>{};annotationHistory=()=>'';
    bindAnnotationEditor(p);
  `,context);
  get('annotation-name').value='烏來社';
  get('annotation-class').value='poi';
  const saving=get('save-annotation').onclick();
  assert.equal(get('save-annotation').disabled,true);
  assert.equal(closed,false); // Never leave before the server confirms success.
  if(outcome==='newer')values='newer edits';
  if(outcome==='failure')reject(Error('Save failed'));
  else resolve({annotation:{ground_truth:'烏來社',classification:'poi'},hidden:false});
  await saving;
  if(outcome==='success'){
    assert.equal(closed,true);assert.equal(refreshed,true);
    assert.equal(p.annotation.ground_truth,'烏來社');
  }else{
    assert.equal(closed,false);assert.equal(get('save-annotation').disabled,false);
    assert.equal(get('annotation-status').textContent,outcome==='failure'?'Save failed':'Saved earlier changes; newer edits are unsaved.');
    assert.equal(refreshed,outcome!=='failure');
  }
}
(async()=>{
  for(const outcome of ['success','failure','newer'])await scenario(outcome);
  console.log('Annotation save: return to map after success; retain editor on failure or newer edits passed.');
})().catch(error=>{console.error(error);process.exitCode=1;});
