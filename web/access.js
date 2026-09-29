'use strict';
let accessState={enabled:false};
const accessReady=fetch('/auth/me').then(async response=>{
  if(response.status===401){requireSignIn();return;}
  if(!response.ok)throw Error('Account status unavailable');
  accessState=await response.json();
  if(accessState.enabled){document.getElementById('account-menu').hidden=false;document.getElementById('account-email').textContent=accessState.email;
    if(accessState.mode==='tailscale'){document.getElementById('sign-out').hidden=true;document.getElementById('account-message').textContent='Private access through Tailscale. Disconnect Tailscale on this device to end access.';}}
}).catch(()=>{document.getElementById('account-message').textContent='Account connection unavailable.';});
function requireSignIn(){sessionStorage.setItem('mapwalker-return',location.pathname+location.search+location.hash);location.assign('/auth/login');}
document.getElementById('sign-out').onclick=async()=>{
  try{const response=await fetch('/auth/logout',{method:'POST',headers:{'X-CSRF-Token':accessState.csrf}});if(!response.ok)throw Error('Could not sign out. Try again.');sessionStorage.removeItem('mapwalker-return');location.replace('/auth/login');}
  catch(error){document.getElementById('account-message').textContent=error.message;}
};
