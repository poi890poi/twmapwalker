const assert=require('node:assert/strict'),vm=require('node:vm'),fs=require('node:fs');
const source=fs.readFileSync('web/live-reload.js','utf8');
async function fixture(){
  const state={revision:'a',dialog:false,hidden:false,reloads:0,timers:[],fail:false,enabled:true};
  vm.runInNewContext(source,{
    document:{get hidden(){return state.hidden},activeElement:null,querySelector:()=>state.dialog?{}:null},
    location:{reload:()=>state.reloads++},
    fetch:async()=>{if(state.fail)throw Error('restarting');return {ok:true,json:async()=>({enabled:state.enabled,revision:state.revision})}},
    setTimeout:fn=>state.timers.push(fn)
  });
  await new Promise(setImmediate);
  state.tick=async()=>{await state.timers.shift()();};
  return state;
}
(async()=>{
  const s=await fixture();assert.equal(s.reloads,0);
  s.dialog=true;s.revision='b';await s.tick();assert.equal(s.reloads,0);
  s.fail=true;await s.tick();assert.equal(s.reloads,0);
  s.fail=false;s.dialog=false;s.hidden=true;await s.tick();assert.equal(s.reloads,0);
  s.hidden=false;await s.tick();assert.equal(s.reloads,1);
  const disabled=await fixture();disabled.enabled=false;await disabled.tick();assert.equal(disabled.timers.length,0);
  console.log('Live refresh: changed revision, edit deferral, reconnect, hidden tab and disabled mode passed.');
})().catch(error=>{console.error(error);process.exitCode=1});
