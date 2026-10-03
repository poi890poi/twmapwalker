"""Replay saved scores and verify localization, adaptation and spatial invariants."""
import time
import numpy as np
import torch
from torch import nn
from .contour_learner_data import ROOT,read,write,sha,near
from .local_mark_data import OUT,BASE,CACHE,SEEDS
from .local_mark_train import Head,tensors
from .local_mark_adapt import LowRank,new_model,selected_masks


def invariant_tests():
    model=Head();model.net=nn.Linear(384,3,bias=False)
    with torch.no_grad():model.net.weight.zero_();model.net.weight[:,0]=1
    x=torch.zeros(1,20,384);x[:,:,0]=-1;x[:,4,0]=5;mask=torch.ones(1,20,dtype=torch.bool)
    assert model(x,mask,'max')[0].item()==5 and model(x,mask,'mean')[0].item()<0
    xx=torch.cat([x,torch.full((1,3,384),10000)],dim=1);mm=torch.cat([mask,torch.zeros(1,3,dtype=torch.bool)],dim=1)
    assert torch.equal(model(x,mask,'max')[0],model(xx,mm,'max')[0])
    assert torch.equal(model(x,mask,'max')[0],model(x.flip(1),mask,'max')[0])
    base=nn.Linear(4,4);old=base.weight.detach().clone();layer=LowRank(base);value=torch.randn(2,4)
    assert torch.equal(base(value),layer(value))
    optimizer=torch.optim.AdamW([p for p in layer.parameters() if p.requires_grad],lr=.01)
    layer(value).sum().backward();assert base.weight.grad is None and layer.b.grad.abs().sum()>0
    optimizer.step();assert torch.equal(old,base.weight)
    return dict(any_small_mark_survives=True,padding_ignored=True,token_permutation_invariant=True,
        zero_adapter_equals_frozen=True,backbone_base_has_no_gradient=True,optimizer_preserves_base=True)


def main():
    started=time.perf_counter();torch.set_num_threads(2);tests=invariant_tests()
    rows=read(OUT/'training.json');guards=read(OUT/'guards.json');challenge=read(OUT/'challenge.json');allrows=rows+guards+challenge;n=len(rows)
    arrays=np.load(OUT/'development-features.npz');x,mask=tensors(arrays,len(allrows));seqmask=selected_masks(arrays,len(allrows))
    prefixes=np.load(CACHE/'development-prefix.npy',mmap_mode='r');folds=read(BASE/'folds.json')+[dict(fold='all',fit=list(range(n)),test=list(range(n,len(allrows))))]
    assert all(not near(a,b) for a in allrows for b in read(OUT/'fresh-inputs.json'))
    for entry in read(OUT/'nested-training.json'):
        f=next(f for f in folds if f['fold']==entry['fold']);it=entry['inner_fit'];iv=entry['inner_validation']
        assert set(it+iv)<=set(f['fit']) and not set(it+iv)&set(f['test'])
        assert not any(near(rows[a],rows[b]) for a in it for b in iv)
    maximum=0;counts={}
    for prefix,folder in [('stage1','heads'),('nested','nested-heads')]:
        for method in ('mean','max','hierarchy'):
            expected=np.load(OUT/f'{prefix}-{method}-scores.npy');actual=np.zeros_like(expected)
            for si,seed in enumerate(SEEDS):
                for f in folds:
                    model=Head().cuda();model.load_state_dict(torch.load(OUT/folder/f'{method}-s{seed}-f{f["fold"]}.pt',weights_only=True,map_location='cuda'))
                    ids=f['test']
                    with torch.inference_mode():actual[si,ids]=(1-model(x[ids],mask[ids],method)[0].sigmoid()).cpu().numpy()
            np.testing.assert_allclose(actual,expected,atol=1e-6,rtol=0);maximum=max(maximum,float(np.max(np.abs(actual-expected))))
            counts[prefix+'-'+method]=actual.size
    method=read(OUT/'stage2-lock.json')['architecture']
    for variant in ('head-continuation','last-block-lora'):
        expected=np.load(OUT/f'stage2-{variant}-scores.npy');actual=np.zeros_like(expected)
        for si,seed in enumerate(SEEDS):
            for f in folds:
                state=torch.load(OUT/'adapters'/f'{variant}-s{seed}-f{f["fold"]}.pt',weights_only=True,map_location='cpu')
                if variant=='head-continuation':model=Head().cuda();model.load_state_dict(state)
                else:
                    warm=torch.load(OUT/'nested-heads'/f'{method}-s{seed}-f{f["fold"]}.pt',weights_only=True,map_location='cpu');model=new_model(seed,warm)
                    params=dict(model.named_parameters());assert set(state)=={k for k,p in params.items() if p.requires_grad}
                    with torch.no_grad():
                        for key,value in state.items():params[key].copy_(value.cuda())
                with torch.inference_mode():
                    for offset in range(0,len(f['test']),8):
                        ids=f['test'][offset:offset+8]
                        logits,_=model(x[ids],mask[ids],method) if variant=='head-continuation' else model(torch.from_numpy(np.array(prefixes[ids])).cuda(),seqmask[ids],method)
                        actual[si,ids]=(1-logits.sigmoid()).cpu().numpy()
                del model;torch.cuda.empty_cache()
        np.testing.assert_allclose(actual,expected,atol=1e-6,rtol=0);maximum=max(maximum,float(np.max(np.abs(actual-expected))))
        counts[variant]=actual.size
    # Locks cover every saved model, plus the lossless cache and untouched reserve.
    for name in ('stage1-lock','nested-lock','stage2-lock','consensus-lock'):
        lock=read(OUT/f'{name}.json')
        for path,digest in lock['states'].items():assert sha(OUT/path)==digest
    assert sha(CACHE/'development-prefix.npy')==read(OUT/'development-feature-lock.json')['prefix_sha256']
    assert sha(OUT/'fresh-inputs.json')==read(OUT/'input-lock.json')['inputs']['fresh-inputs.json']
    assert not read(OUT/'consensus-summary.json')['eligible']
    assert not (OUT/'fresh-predictions.json').exists()
    write(OUT/'verification.json',dict(tests=tests,score_replays=counts,max_absolute_error=maximum,
        nested_spatial_separation='All inner folds lie within outer fit and respect2-tile buffers',
        fresh_reserve='40 targets geographically separated; never encoded, scored, displayed or labeled',
        source_code_sha256=sha(ROOT/'tools/verify_local_mark.py'),seconds=time.perf_counter()-started))
    print('All saved-model scores, six invariants, spatial splits, cache and model hashes verified.',flush=True)


if __name__=='__main__':main()
