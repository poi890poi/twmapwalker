"""Paired spatial trials: pooling first, then weak text/symbol bag supervision."""
import time
import numpy as np
import torch
from torch import nn
from .contour_learner_data import ROOT,read,write,sha
from .local_mark_data import OUT,BASE,SEEDS


class Head(nn.Module):
    def __init__(self):
        super().__init__();self.net=nn.Sequential(nn.Linear(384,64),nn.GELU(),nn.Linear(64,3))
    def forward(self,x,mask,method):
        logits=self.net(x)
        if method=='mean':pooled=(logits*mask[:,:,None]).sum(1)/mask.sum(1)[:,None]
        else:pooled=logits.masked_fill(~mask[:,:,None],-1e4).max(1).values
        return pooled.max(1).values,pooled


def target_labels(rows):
    y=torch.tensor([not r['negative'] for r in rows],dtype=torch.float32,device='cuda')
    fine=torch.full((len(rows),2),float('nan'),device='cuda')
    for i,r in enumerate(rows):
        if r['negative']:fine[i]=0
        elif r['label'] in ('numeric','text','kana','han'):fine[i,0]=1
        elif r['label'] in ('vegetation-like','vegetation','other-repeated-symbol','protected-symbol'):fine[i,1]=1
    return y,fine


def balanced(logits,y):
    loss=nn.functional.binary_cross_entropy_with_logits(logits,y,reduction='none')
    groups=[loss[y==v].mean() for v in (0,1) if (y==v).any()]
    return torch.stack(groups).mean()


def objective(logits,pooled,y,fine,method):
    loss=balanced(logits,y)
    if method=='hierarchy':
        parts=[]
        for c in range(2):
            available=torch.isfinite(fine[:,c])
            if available.any():parts.append(balanced(pooled[available,c+1],fine[available,c]))
        loss=loss+.25*torch.stack(parts).mean()
    return loss


def tensors(arrays,count):
    size=max(len(arrays[f'p{i}']) for i in range(count));x=np.zeros((count,size,384),np.float32);mask=np.zeros((count,size),bool)
    for i in range(count):
        p=arrays[f'p{i}'];x[i,:len(p)]=p;mask[i,:len(p)]=True
    return torch.from_numpy(x).cuda(),torch.from_numpy(mask).cuda()


def summarize(scores,rows,guards,challenge):
    # scores: seeds x (trainingOOF + guards + consumed challenge)
    n=len(rows);g=len(guards);allrows=rows+guards+challenge;mean=np.mean(scores,axis=0)
    def metric(v):
        threshold=float(max(v[i] for i,r in enumerate(rows) if not r['negative'])+.025);flag=v>threshold
        return dict(threshold=threshold,contour_hits=sum(bool(flag[i] and r['negative']) for i,r in enumerate(rows)),
            hits1924=sum(bool(flag[i] and r['negative']) for i,r in enumerate(rows) if '1924' in r['source']),
            protected_oof_flags=sum(bool(flag[i] and not r['negative']) for i,r in enumerate(rows)),
            guard_flags=int(flag[n:n+g].sum()),challenge_contour_hits=sum(bool(flag[n+g+i] and r['negative']) for i,r in enumerate(challenge)),
            challenge_protected_flags=sum(bool(flag[n+g+i] and not r['negative']) for i,r in enumerate(challenge)))
    s=metric(mean);s['per_seed']=[metric(v) for v in scores]
    s['eligible']=s['contour_hits']>=24 and s['hits1924']>2 and s['guard_flags']==0 and s['challenge_protected_flags']==0
    return s,[dict(id=r['id'],label=r['label'],negative=r['negative'],source=r.get('source','reference-control'),score=float(v),reject=bool(v>s['threshold'])) for r,v in zip(allrows,mean)]


def main():
    if (OUT/'stage1-lock.json').exists():raise RuntimeError('Stage1 locked')
    torch.set_num_threads(2);(OUT/'heads').mkdir(exist_ok=True)
    rows=read(OUT/'training.json');guards=read(OUT/'guards.json');challenge=read(OUT/'challenge.json');allrows=rows+guards+challenge
    lock=read(OUT/'development-feature-lock.json');assert sha(OUT/'development-features.npz')==lock['arrays_sha256']
    arrays=np.load(OUT/'development-features.npz');x,mask=tensors(arrays,len(allrows));y,fine=target_labels(rows)
    folds=read(BASE/'folds.json')+[dict(fold='all',fit=list(range(len(rows))),test=list(range(len(rows),len(allrows))))]
    summaries={};outputs={};histories=[];states={}
    for method in ('mean','max','hierarchy'):
        seed_scores=[]
        for seed in SEEDS:
            scores=np.zeros(len(allrows))
            for fold in folds:
                torch.manual_seed(seed);model=Head().cuda();optimizer=torch.optim.AdamW(model.parameters(),lr=.003,weight_decay=.01)
                tr=fold['fit'];te=fold['test'];xx=x[tr];mm=mask[tr];yy=y[tr];ff=fine[tr]
                history=[];torch.cuda.synchronize();start=time.perf_counter()
                for epoch in range(200):
                    optimizer.zero_grad();logits,pooled=model(xx,mm,method);loss=objective(logits,pooled,yy,ff,method)
                    loss.backward();optimizer.step()
                    if epoch in (0,49,99,199):history.append(dict(epoch=epoch+1,loss=float(loss.detach())))
                model.eval()
                with torch.inference_mode():scores[te]=(1-model(x[te],mask[te],method)[0].sigmoid()).cpu().numpy()
                torch.cuda.synchronize();elapsed=time.perf_counter()-start
                path=OUT/'heads'/f'{method}-s{seed}-f{fold["fold"]}.pt';torch.save({k:v.cpu() for k,v in model.state_dict().items()},path)
                states[path.relative_to(OUT).as_posix()]=sha(path)
                histories.append(dict(method=method,seed=seed,fold=fold['fold'],seconds=elapsed,loss=history))
                print(method,seed,fold['fold'],f'{elapsed:.1f}s',f'loss {history[-1]["loss"]:.4f}',flush=True)
            seed_scores.append(scores)
        scores=np.stack(seed_scores);scorepath=OUT/f'stage1-{method}-scores.npy'
        if scorepath.exists():np.testing.assert_array_equal(scores,np.load(scorepath))
        else:np.save(scorepath,scores)
        summaries[method],outputs[method]=summarize(scores,rows,guards,challenge)
        print('RESULT',method,summaries[method],flush=True)
    selected=min(summaries,key=lambda m:(summaries[m]['challenge_protected_flags'],-summaries[m]['hits1924'],-summaries[m]['contour_hits']))
    write(OUT/'stage1-summary.json',summaries);write(OUT/'stage1-predictions.json',outputs);write(OUT/'stage1-training.json',histories)
    write(OUT/'stage1-lock.json',dict(selected=selected,states=states,code_sha256=sha(ROOT/'tools/local_mark_train.py'),
        feature_lock_sha256=sha(OUT/'development-feature-lock.json'),fresh_sha256=sha(OUT/'fresh-inputs.json'),
        interpretation='No fresh evaluation yet; consumed48 failure set influences architecture selection and is not independent evidence.'))
    print('Selected architecture for paired adaptation:',selected,flush=True)


if __name__=='__main__':main()
