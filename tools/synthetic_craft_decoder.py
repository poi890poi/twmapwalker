"""Second controlled adaptation: same synthetic corpus, train the decoder too."""
import hashlib,json,random,sys,time
from pathlib import Path
import numpy as np,torch
import torch.nn.functional as F
from easyocr.detection import get_detector
from easyocr.imgproc import normalizeMeanVariance
from synthetic_craft import ROOT,FONTS,sample
OUT=ROOT/'data/model-trials/synthetic-craft-v2'

def main():
    if (OUT/'adapted.pth').exists():raise RuntimeError('Preserve completed checkpoint')
    OUT.mkdir(parents=True,exist_ok=True);torch.set_num_threads(2);torch.manual_seed(3081);rng=random.Random(3081)
    weights=ROOT/'data/model-trials/models/easyocr/craft_mlt_25k.pth'
    model=get_detector(str(weights),device='cuda');net=model.module if hasattr(model,'module') else model
    net.eval()
    for p in net.basenet.parameters():p.requires_grad_(False)
    torch.cuda.reset_peak_memory_stats();features=[];targets=[];tick=time.perf_counter()
    for i in range(256):
        im,target,boxes=sample(rng)
        x=torch.from_numpy(normalizeMeanVariance(np.asarray(im)).transpose(2,0,1)[None]).cuda()
        with torch.no_grad():sources=net.basenet(x)
        features.append([f[0].half().cpu() for f in sources]);targets.append(torch.from_numpy(target).half())
        if i%64==0:print('generated',i,flush=True)
    prepare_seconds=time.perf_counter()-tick;opt=torch.optim.Adam([p for p in net.parameters() if p.requires_grad],lr=1e-4)
    losses=[];tick=time.perf_counter()
    for step in range(1200):
        indices=rng.sample(range(len(features)),4)
        sources=[torch.stack([features[i][j] for i in indices]).float().cuda() for j in range(5)]
        target=torch.stack([targets[i] for i in indices]).float().cuda()
        y=net.upconv1(torch.cat([sources[0],sources[1]],dim=1))
        for j,layer in [(2,net.upconv2),(3,net.upconv3),(4,net.upconv4)]:
            y=F.interpolate(y,size=sources[j].shape[2:],mode='bilinear',align_corners=False)
            y=layer(torch.cat([y,sources[j]],dim=1))
        pred=net.conv_cls(y)[:,0];loss_map=(pred-target).square();positive=target>.10
        pos=loss_map[positive].mean() if positive.any() else pred.sum()*0
        neg=loss_map[~positive];hard=neg.topk(min(neg.numel(),max(500,int(positive.sum())*3))).values.mean()
        loss=pos+hard;opt.zero_grad();loss.backward();opt.step()
        if step%100==0:
            losses.append(dict(step=step,loss=float(loss.detach())));print('step',step,round(float(loss.detach()),4),flush=True)
    torch.save(net.state_dict(),OUT/'adapted.pth')
    meta=dict(seed=3081,samples=256,steps=1200,batch=4,learning_rate=1e-4,trainable='upconv1-4 and conv_cls; backbone and batchnorm statistics frozen',prepare_seconds=prepare_seconds,train_seconds=time.perf_counter()-tick,losses=losses,peak_allocated_mib=torch.cuda.max_memory_allocated()/1024**2,base_sha256=hashlib.sha256(weights.read_bytes()).hexdigest(),checkpoint_sha256=hashlib.sha256((OUT/'adapted.pth').read_bytes()).hexdigest(),fonts={str(p):hashlib.sha256(p.read_bytes()).hexdigest() for p in FONTS},harness_sha256=hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),generator_sha256=hashlib.sha256((ROOT/'tools/synthetic_craft.py').read_bytes()).hexdigest())
    (OUT/'run.json').write_text(json.dumps(meta,indent=2));(OUT/'harness.py').write_bytes(Path(__file__).read_bytes())
    print('complete',meta['train_seconds'],meta['peak_allocated_mib'],flush=True)
if __name__=='__main__':main()
