"""Choose training duration using buffered inner geography, never outer-fold labels."""
import time
import numpy as np
import torch
from .contour_learner_data import ROOT,read,write,sha,near
from .local_mark_data import OUT,BASE,SEEDS
from .local_mark_train import Head,tensors,target_labels,objective,balanced,summarize


def inner_split(fold,folds,rows):
    candidates=[(int(fold['fold'])+i)%5 for i in range(1,5)] if fold['fold']!='all' else list(range(5))
    for k in candidates:
        val=sorted(set(fold['fit'])&set(folds[k]['test']))
        fit=[i for i in fold['fit'] if i not in val and not any(near(rows[i],rows[j]) for j in val)]
        if len(val)>=12 and len(fit)>=35 and len({rows[i]['negative'] for i in val})==2 and len({rows[i]['negative'] for i in fit})==2:return fit,val
    raise RuntimeError('No valid buffered inner split')


def main():
    if (OUT/'nested-lock.json').exists():raise RuntimeError('Nested experiment locked')
    write(OUT/'nested-contract.json',dict(reason='Fixed200-epoch heads overfit and saturate protected OOF scores. Preserve their results; test geography-selected training duration as a separate change.',
        methods=['mean','max','hierarchy'],settings='Same head,optimizer,loss,seeds and outer folds. Inner validation uses one other geographic fold, with2-tile buffer within outer fitting set. Evaluate broad balanced BCE every5epochs up to200, patience8checks. Refit from scratch on whole outer fit for chosen epoch count.',
        selection='Same predeclared architecture ranking and thresholds as stage1. No fresh data viewed or scored.',
        adaptation='Use the selected nested head as initialization for the two paired continuation variants. This replaces adaptation of already overfit fixed200-epoch heads; preserve original contract and document change.',
        causal_rule='Inner validation must be a subset of outer fit; outer test,58 guards,48 known challenges and40 fresh crops never select epochs.'))
    torch.set_num_threads(2);(OUT/'nested-heads').mkdir(exist_ok=True)
    rows=read(OUT/'training.json');guards=read(OUT/'guards.json');challenge=read(OUT/'challenge.json');allrows=rows+guards+challenge
    arrays=np.load(OUT/'development-features.npz');x,mask=tensors(arrays,len(allrows));y,fine=target_labels(rows)
    outer=read(BASE/'folds.json');folds=outer+[dict(fold='all',fit=list(range(len(rows))),test=list(range(len(rows),len(allrows))))]
    summaries={};outputs={};history=[];states={}
    for method in ('mean','max','hierarchy'):
        seed_scores=[]
        for seed in SEEDS:
            scores=np.zeros(len(allrows))
            for fold in folds:
                it,iv=inner_split(fold,outer,rows);assert not set(it+iv)&set(fold['test'])
                torch.manual_seed(seed);model=Head().cuda();optimizer=torch.optim.AdamW(model.parameters(),lr=.003,weight_decay=.01)
                xx=x[it];mm=mask[it];yy=y[it];ff=fine[it];best=float('inf');chosen=None;stale=0;curve=[];start=time.perf_counter()
                for epoch in range(200):
                    optimizer.zero_grad();logits,pooled=model(xx,mm,method);loss=objective(logits,pooled,yy,ff,method);loss.backward();optimizer.step()
                    if (epoch+1)%5==0:
                        with torch.inference_mode():value=float(balanced(model(x[iv],mask[iv],method)[0],y[iv]))
                        curve.append(dict(epoch=epoch+1,validation_loss=value))
                        if value<best:best=value;chosen=epoch+1;stale=0
                        else:stale+=1
                        if stale>=8:break
                torch.manual_seed(seed);model=Head().cuda();optimizer=torch.optim.AdamW(model.parameters(),lr=.003,weight_decay=.01)
                tr=fold['fit'];xx=x[tr];mm=mask[tr];yy=y[tr];ff=fine[tr]
                for _ in range(chosen):
                    optimizer.zero_grad();logits,pooled=model(xx,mm,method);loss=objective(logits,pooled,yy,ff,method);loss.backward();optimizer.step()
                with torch.inference_mode():scores[fold['test']]=(1-model(x[fold['test']],mask[fold['test']],method)[0].sigmoid()).cpu().numpy()
                path=OUT/'nested-heads'/f'{method}-s{seed}-f{fold["fold"]}.pt';torch.save({k:v.cpu() for k,v in model.state_dict().items()},path);states[path.relative_to(OUT).as_posix()]=sha(path)
                history.append(dict(method=method,seed=seed,fold=fold['fold'],inner_fit=it,inner_validation=iv,epochs=chosen,curve=curve,seconds=time.perf_counter()-start))
                print('nested',method,seed,fold['fold'],'epochs',chosen,flush=True)
            seed_scores.append(scores)
        scores=np.stack(seed_scores);np.save(OUT/f'nested-{method}-scores.npy',scores);summaries[method],outputs[method]=summarize(scores,rows,guards,challenge)
        print('RESULT nested',method,summaries[method],flush=True)
    selected=min(summaries,key=lambda m:(summaries[m]['challenge_protected_flags'],-summaries[m]['hits1924'],-summaries[m]['contour_hits']))
    write(OUT/'nested-summary.json',summaries);write(OUT/'nested-predictions.json',outputs);write(OUT/'nested-training.json',history)
    write(OUT/'nested-lock.json',dict(selected=selected,states=states,code_sha256=sha(ROOT/'tools/local_mark_nested.py'),
        head_code_sha256=sha(ROOT/'tools/local_mark_train.py'),contract_sha256=sha(OUT/'nested-contract.json'),fresh_sha256=sha(OUT/'fresh-inputs.json')))


if __name__=='__main__':main()
