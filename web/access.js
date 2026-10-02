'use strict';
let accessState={enabled:false};
let accessLoaded=false,accessRefresh=null;
function refreshAccess(){
  if(!accessRefresh)accessRefresh=(async()=>{
    const response=await fetch('/auth/me',{cache:'no-store'});
    if(response.status===401){const error=Error('Session expired. Keep this page open, sign in in another tab, then try saving again.');error.status=401;throw error;}
    if(!response.ok)throw Error('Account connection unavailable. Your changes are still here; try saving again.');
    accessState=await response.json();accessLoaded=true;
    if(accessState.enabled){document.getElementById('account-menu').hidden=false;document.getElementById('account-email').textContent=accessState.email;
      if(accessState.mode==='tailscale'){document.getElementById('sign-out').hidden=true;document.getElementById('account-message').textContent='Private access through Tailscale. Disconnect Tailscale on this device to end access.';}}
  })().finally(()=>{accessRefresh=null;});
  return accessRefresh;
}
const accessReady=refreshAccess().catch(error=>{
  if(error.status===401)requireSignIn();
  document.getElementById('account-message').textContent='Account connection unavailable.';
});
async function accessFetch(url,options={}){
  await accessReady;
  const writing=['POST','PUT','PATCH','DELETE'].includes((options.method||'GET').toUpperCase());
  if(writing&&!accessLoaded)await refreshAccess();
  const before=accessState;
  const send=()=>{
    const headers=new Headers(options.headers);
    if(writing&&accessState.enabled)headers.set('X-CSRF-Token',accessState.csrf);
    return fetch(url,{...options,headers});
  };
  let response=await send();
  if(writing&&response.status===403){
    const error=await response.clone().json().catch(()=>null);
    if(error?.code==='csrf_expired'){
      // Retry only an explicit rejection before mutation, never network/5xx failures.
      // Share concurrent refreshes and retain the original serialized request body.
      if(accessState===before)await refreshAccess();
      if(accessState.enabled!==before.enabled||accessState.email!==before.email||accessState.mode!==before.mode)
        throw Error('The signed-in account changed. Your edits are still here; check Account before saving again.');
      response=await send();
      if(response.status===403&&(await response.clone().json().catch(()=>null))?.code==='csrf_expired')
        throw Error('Save security could not be renewed. Your edits are still here; try saving again.');
    }
  }
  return response;
}
function requireSignIn(){sessionStorage.setItem('mapwalker-return',location.pathname+location.search+location.hash);location.assign('/auth/login');}
document.getElementById('sign-out').onclick=async()=>{
  try{const response=await accessFetch('/auth/logout',{method:'POST'});if(!response.ok)throw Error('Could not sign out. Try again.');sessionStorage.removeItem('mapwalker-return');location.replace('/auth/login');}
  catch(error){document.getElementById('account-message').textContent=error.message;}
};
