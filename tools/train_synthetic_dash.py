"""Frozen synthetic-only experiment on the existing GTX 1650."""
import hashlib,json,sys,time
from pathlib import Path
import cv2,numpy as np,torch
from PIL import Image
from torch.nn import functional as F
from synthetic_dash_model import DashNet,sample
ROOT=Path(__file__).resolve().parents[1];OUT=ROOT/'evidence/trail-round5';DATA=ROOT/'data/trail-round5'

def main():
    global OUT,DATA,sample
    variant='worn' if '--worn' in sys.argv else 'base'
    if variant=='worn':
        from synthetic_dash_worn import sample
        OUT=OUT/'worn';DATA=DATA/'worn';OUT.mkdir(exist_ok=True)
    DATA.mkdir(exist_ok=True);target=DATA/'dashnet.pt'
    if target.exists():raise RuntimeError('Preserve frozen checkpoint')
    torch.set_num_threads(2);torch.manual_seed(5101);np.random.seed(5101)
    start=time.perf_counter();pairs=[sample(510000+i) for i in range(1024)];validation=[sample(610000+i) for i in range(128)]
    xs=torch.from_numpy(np.stack([a for a,b in pairs])).float()[:,None]/255;ys=torch.from_numpy(np.stack([b for a,b in pairs])).float()[:,None]
    generation=time.perf_counter()-start
    board=np.zeros((4*192,8*192,3),np.uint8)
    for i,(a,b) in enumerate(pairs[:16]):
        row,col=divmod(i,4);board[row*192:(row+1)*192,col*384:col*384+192]=a[:,:,None]
        over=np.repeat(a[:,:,None],3,2);over[b]=[230,35,80];board[row*192:(row+1)*192,col*384+192:(col+1)*384]=over
    Image.fromarray(board).save(OUT/'synthetic-training-examples.png')
    model=DashNet().cuda();opt=torch.optim.AdamW(model.parameters(),lr=.001);losses=[]
    torch.cuda.reset_peak_memory_stats();torch.cuda.synchronize();start=time.perf_counter()
    rng=np.random.default_rng(5101)
    for step in range(1000):
        ix=rng.integers(0,len(xs),8);x=xs[ix].cuda();y=ys[ix].cuda();p=model(x)
        bce=F.binary_cross_entropy_with_logits(p,y,pos_weight=torch.tensor(5.,device='cuda'))
        q=p.sigmoid();dice=1-(2*(q*y).sum()+1)/(q.sum()+y.sum()+1);loss=bce+dice
        opt.zero_grad(set_to_none=True);loss.backward();opt.step()
        if step%100==0:losses.append(dict(step=step,loss=float(loss.detach())));print(step,round(losses[-1]['loss'],4),flush=True)
    torch.cuda.synchronize();training=time.perf_counter()-start;model.eval();torch.save(model.cpu().state_dict(),target);model.cuda()
    tp=fp=fn=0
    with torch.inference_mode():
        for a,b in validation:
            p=model(torch.from_numpy(a.copy()).float()[None,None].cuda()/255).sigmoid()[0,0].cpu().numpy()>=.5
            tp+=int((p&b).sum());fp+=int((p&~b).sum());fn+=int((~p&b).sum())
    result=dict(variant=variant,device=torch.cuda.get_device_name(),torch=torch.__version__,parameters=sum(p.numel() for p in model.parameters()),generation_s=generation,training_s=training,steps=1000,batch=8,seed=5101,train_samples=1024,validation_samples=128,synthetic_precision=tp/max(1,tp+fp),synthetic_recall=tp/max(1,tp+fn),tp=tp,fp=fp,fn=fn,losses=losses,peak_allocated_mb=torch.cuda.max_memory_allocated()/2**20,weights_sha256=hashlib.sha256(target.read_bytes()).hexdigest(),code_sha256=hashlib.sha256((ROOT/'tools/synthetic_dash_model.py').read_bytes()).hexdigest())
    if variant=='worn':result['augmentation_sha256']=hashlib.sha256((ROOT/'tools/synthetic_dash_worn.py').read_bytes()).hexdigest()
    (OUT/'training.json').write_text(json.dumps(result,indent=2));print(json.dumps(result),flush=True)

if __name__=='__main__':
    import urllib.request
    base='http://127.0.0.1:8765/api/'
    with urllib.request.urlopen(base+'status',timeout=10) as r:before=json.load(r)
    def pause(value):
        req=urllib.request.Request(base+'worker/pause',data=json.dumps({'paused':value}).encode(),headers={'Content-Type':'application/json'})
        with urllib.request.urlopen(req,timeout=10) as r:return r.read()
    original=bool(before['paused'])
    try:
        pause(True);main()
    finally:pause(original)
