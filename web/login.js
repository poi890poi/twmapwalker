'use strict';
const message=document.getElementById('login-status'),retry=document.getElementById('retry-login');
let loginConfig;
function failure(text){message.textContent=text;message.classList.add('error');retry.hidden=false;}
function destination(){
  const requested=new URLSearchParams(location.search).get('next')||'/';
  const safe=requested.startsWith('/')&&!requested.startsWith('//')&&!requested.includes('\\')?requested:'/';
  const remembered=sessionStorage.getItem('mapwalker-return');sessionStorage.removeItem('mapwalker-return');
  if(remembered?.startsWith('/')&&!remembered.startsWith('//')&&!remembered.includes('\\'))return remembered;
  return safe+location.hash;
}
async function signedIn(result){
  message.classList.remove('error');message.textContent='Checking your access…';retry.hidden=true;
  try{
    const response=await fetch('/auth/google',{method:'POST',headers:{'Content-Type':'application/json','X-CSRF-Token':loginConfig.nonce},body:JSON.stringify({credential:result.credential})});
    const value=await response.json();if(!response.ok)throw Error(value.detail||'Unable to sign in.');
    location.replace(destination());
  }catch(error){failure(error.message);}
}
async function prepare(){
  try{
    const response=await fetch('/auth/config',{cache:'no-store'});loginConfig=await response.json();
    if(!response.ok)throw Error(loginConfig.detail||'Sign-in is unavailable.');
    if(!loginConfig.enabled){location.replace('/');return;}
    const initialize=()=>{
      google.accounts.id.initialize({client_id:loginConfig.client_id,callback:signedIn,nonce:loginConfig.nonce,auto_select:false});
      google.accounts.id.renderButton(document.getElementById('google-signin'),{type:'standard',theme:'outline',size:'large',text:'signin_with',shape:'pill',width:Math.min(320,document.getElementById('google-signin').clientWidth)});
      message.textContent='Only accounts approved by the project owner can enter.';
    };
    if(window.google?.accounts?.id)initialize();
    else{const script=document.createElement('script');script.src='https://accounts.google.com/gsi/client';script.onload=initialize;script.onerror=()=>failure('Google sign-in could not load. Check your connection and try again.');document.head.append(script);}
  }catch(error){failure(error.message);}
}
retry.onclick=()=>location.reload();prepare();
