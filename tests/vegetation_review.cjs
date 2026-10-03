const assert=require('node:assert/strict');
const {vegetationReviewState}=require('../web/vegetation-review.js');
const items=[{id:1,input_key:'a'},{id:2,input_key:'b'}];
const requests=[],updates=[];
const review=vegetationReviewState((url,payload)=>new Promise((resolve,reject)=>requests.push({url,payload,resolve,reject})),s=>updates.push(s.busy));
(async()=>{
 let pending=review.load();assert(review.state.busy);requests.shift().resolve({profile:'v1',items,next_after:2});await pending;
 assert.equal(review.state.selected.size,0);
 await review.decide('other');assert.equal(requests.length,0);
 review.select([1,999]);assert.deepEqual([...review.state.selected],[1]);
 pending=review.decide('other');const save=requests.shift();assert.deepEqual(save.payload,{profile:'v1',items:[items[0]],outcome:'other'});
 review.select([2]);assert.deepEqual([...review.state.selected],[1]); // Frozen while saving.
 save.reject(Error('Changed proposal; nothing saved'));await pending;
 assert.deepEqual([...review.state.selected],[1]);assert.match(review.state.message,/nothing saved/);
 pending=review.decide('dismiss');requests.shift().resolve({saved:1});
 await new Promise(resolve=>setImmediate(resolve));
 assert.equal(review.state.selected.size,0);requests.shift().resolve({profile:'v1',items:[items[1]],next_after:null});await pending;
 assert.match(review.state.message,/unchanged/);assert(!review.state.busy);
 review.select([2]);pending=review.load(2,[0]);requests.shift().reject(Error('Network down'));await pending;
 assert.equal(review.state.after,0);assert.deepEqual([...review.state.selected],[2]);
 assert.deepEqual(review.state.history,[]);
 console.log('Vegetation queue: empty selection, explicit bounded payload, write lock, failed-save retention, dismissal and failed navigation pass.');
})().catch(e=>{console.error(e);process.exitCode=1;});
