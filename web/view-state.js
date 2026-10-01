'use strict';
const MapwalkerState = (() => {
  const key='mapwalker-view-v1';
  const choices={source:['JM50K_1924_new','JM50K_1916'],comparison:['nlsc','osm','rudy'],
    display:['top','reduced','all','adaptive'],kind:['all','text','symbol'],
    review:['all','unreviewed','confirmed','uncertain','rejected'],reading:['all','named','unread'],
    sort:['priority','name','newest','score'],'page-size':['25','50','100']};
  function clean(value){
    const input=new URLSearchParams(value),out=new URLSearchParams();
    for(const [name,allowed] of Object.entries(choices))if(allowed.includes(input.get(name)))out.set(name,input.get(name));
    for(const [name,min,max] of [['lat',19,29],['lon',115,126],['z',5,19],['opacity',0,100],['page',1,100000]]){
      const raw=input.get(name),n=Number(raw);
      if(raw!==null&&raw.trim()!==''&&Number.isFinite(n)&&n>=min&&n<=max)out.set(name,['z','page'].includes(name)?Math.round(n):n);
    }
    if(!['lat','lon','z'].every(name=>out.has(name)))for(const name of ['lat','lon','z'])out.delete(name);
    for(const name of ['excluded','osm','grid'])if(['0','1'].includes(input.get(name)))out.set(name,input.get(name));
    if(input.has('q'))out.set('q',input.get('q').slice(0,80));
    return out;
  }
  function load(hash,getStorage){
    const link=clean(hash.replace(/^#/,''));
    try{
      const storage=getStorage(),record=JSON.parse(storage.getItem(key));
      if(record?.version===1&&typeof record.params==='string'){
        const ui={};for(const name of ['list','layers','filters','jobs'])ui[name]=record.ui?.[name]===true;
        const params=clean(record.params);
        if(link.size)return {params:link,ui:link.toString()===params.toString()?ui:{}};
        return {params,ui};
      }
    }catch{}
    if(link.size)return {params:link,ui:{}};
    const params=new URLSearchParams();
    try{const display=getStorage().getItem('mapwalker-display');if(choices.display.includes(display))params.set('display',display);}catch{}
    return {params,ui:{}};
  }
  function save(params,ui,getStorage){
    try{getStorage().setItem(key,JSON.stringify({version:1,params:clean(params).toString(),ui}));return true;}catch{return false;}
  }
  return Object.freeze({load,save});
})();
if(typeof module!=='undefined')module.exports=MapwalkerState;
