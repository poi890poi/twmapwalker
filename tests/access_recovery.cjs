// Exercise the shipped access helper and API wrapper with a rotating session.
const assert=require('node:assert/strict'),fs=require('node:fs'),vm=require('node:vm');
const app=fs.readFileSync('web/app.js','utf8');
const apiSource=app.slice(app.indexOf('async function api('),app.indexOf('function label('));
async function scenario({failure,parallel=false,initialFailure=false}={}){
  let authCalls=0,writes=0,applied=0,redirects=0;
  const bodies=[],tokens=[];
  const elements=new Map(),get=id=>{if(!elements.has(id))elements.set(id,{});return elements.get(id);};
  const context=vm.createContext({Headers,document:{getElementById:get},sessionStorage:{setItem(){},removeItem(){}},
    location:{assign(){redirects++;},replace(){redirects++;}},MapwalkerView:{error:message=>message},
    fetch:async(url,options={})=>{
      if(url==='/auth/me'){
        authCalls++;
        if((initialFailure&&authCalls===1)||(failure==='refresh'&&authCalls>1))throw Error('Offline');
        if(failure==='signed-out'&&authCalls>1)return new Response('{}',{status:401});
        return new Response(JSON.stringify({enabled:true,mode:'tailscale',email:failure==='identity'&&authCalls>1?'other@example.com':'owner@example.com',csrf:authCalls===1?'old':'fresh'}));
      }
      writes++;bodies.push(options.body);tokens.push(options.headers.get('X-CSRF-Token'));
      if(failure==='network')throw Error('Network interrupted');
      if(failure==='server')return new Response('{"detail":"Server error"}',{status:500});
      if(failure==='forbidden')return new Response('{"detail":"Cross-origin writes are disabled."}',{status:403});
      if(tokens.at(-1)==='old'||failure==='repeated')return new Response('{"code":"csrf_expired","detail":"Refresh this page before making changes."}',{status:403});
      applied++;
      return new Response('{"saved":true}');
    }});
  vm.runInContext(fs.readFileSync('web/access.js','utf8')+'\n'+apiSource,context);
  const body={ground_truth:'模故山',map_direction:'vertical',osm_type:'node',osm_id:5588811553,note:'Draft'};
  context.body=body;
  const call=()=>vm.runInContext("post('/api/pois/1/annotation',body)",context);
  if(failure){await assert.rejects(call());assert.equal(applied,0);}
  else if(parallel){await Promise.all([call(),call()]);assert.equal(applied,2);}
  else{assert.equal((await call()).saved,true);assert.equal(applied,1);}
  assert.equal(redirects,0,'Recovery must retain the open editor');
  assert(bodies.every(value=>value===JSON.stringify(body)),'Retry must keep the exact submitted fields');
  assert.equal(authCalls,['network','server','forbidden'].includes(failure)?1:2);
  assert.equal(writes,parallel?4:initialFailure?1:failure==='repeated'||!failure?2:1);
}
(async()=>{
  await scenario();await scenario({parallel:true});await scenario({initialFailure:true});
  for(const failure of ['refresh','signed-out','identity','network','server','forbidden','repeated'])await scenario({failure});
  console.log('Access recovery: stale session, shared refresh, intact payload, bounded retry and failure safety passed.');
})().catch(error=>{console.error(error);process.exitCode=1;});
