"""Matched continuation versus rank4 adaptation of the final DINO attention block."""
import math
import time
import numpy as np
import torch
from torch import nn
from transformers import AutoModel
from .contour_learner_data import ROOT,read,write,sha
from .noise_methods_features import WEIGHTS
from .local_mark_data import OUT,BASE,CACHE,SEEDS
from .local_mark_train import Head,tensors,target_labels,objective,summarize


class LowRank(nn.Module):
    def __init__(self,base):
        super().__init__();self.base=base;self.a=nn.Parameter(torch.empty(4,base.in_features));self.b=nn.Parameter(torch.zeros(base.out_features,4))
        nn.init.kaiming_uniform_(self.a,a=math.sqrt(5))
        for p in base.parameters():p.requires_grad_(False)
    def forward(self,x):return self.base(x)+(x@self.a.T)@self.b.T


class Adapted(nn.Module):
    def __init__(self,encoder,head):
        super().__init__();self.block=encoder.encoder.layer[-1];self.norm=encoder.layernorm;self.head=head
        for p in self.parameters():p.requires_grad_(False)
        attention=self.block.attention.attention
        attention.query=LowRank(attention.query);attention.value=LowRank(attention.value)
        for p in self.head.parameters():p.requires_grad_(True)
    def forward(self,x,mask,method):
        tokens=nn.functional.normalize(self.norm(self.block(x)),dim=-1)
        return self.head(tokens,mask,method)


def new_model(seed,head_state):
    torch.manual_seed(seed)
    encoder=AutoModel.from_pretrained(str(WEIGHTS),local_files_only=True).eval()
    head=Head();head.load_state_dict(head_state)
    return Adapted(encoder,head).cuda()


def selected_masks(arrays,count):
    masks=np.zeros((count,785),bool)
    for i in range(count):masks[i,arrays[f'i{i}']]=True
    return torch.from_numpy(masks).cuda()


def state_trainable(model):
    return {name:p.detach().cpu() for name,p in model.named_parameters() if p.requires_grad}


def main():
    if (OUT/'stage2-lock.json').exists():raise RuntimeError('Stage2 locked')
    torch.set_num_threads(2);startall=time.perf_counter();(OUT/'adapters').mkdir(exist_ok=True)
    first=read(OUT/'nested-lock.json');method=first['selected']
    nested=read(OUT/'nested-summary.json')
    tied=all((s['challenge_protected_flags'],s['hits1924'],s['contour_hits'])==
             (nested[method]['challenge_protected_flags'],nested[method]['hits1924'],nested[method]['contour_hits']) for s in nested.values())
    if tied:method='max'
    write(OUT/'stage2-plan.json',dict(architecture=method,tie_break='Prefer localized max pooling without extra fine-label loss when all predeclared metrics tie',
        reason='All nested models currently abstain at the margin cutoff. Test whether limited backbone adaptation improves representation, with matched head-only continuation.',
        source_head_lock_sha256=sha(OUT/'nested-lock.json'),settings='Original20epoch,rank4,q/v-only,three-seed paired adaptation settings retained; fresh reserve untouched'))
    assert sha(ROOT/'tools/local_mark_train.py')==first['head_code_sha256']
    assert sha(ROOT/'tools/local_mark_nested.py')==first['code_sha256']
    fl=read(OUT/'development-feature-lock.json');assert sha(CACHE/'development-prefix.npy')==fl['prefix_sha256']
    rows=read(OUT/'training.json');guards=read(OUT/'guards.json');challenge=read(OUT/'challenge.json');count=len(rows+guards+challenge)
    arrays=np.load(OUT/'development-features.npz');x,mask=tensors(arrays,count);seqmask=selected_masks(arrays,count)
    prefixes=np.load(CACHE/'development-prefix.npy',mmap_mode='r');y,fine=target_labels(rows)
    folds=read(BASE/'folds.json')+[dict(fold='all',fit=list(range(len(rows))),test=list(range(len(rows),count)))]
    summaries={};outputs={};histories=[];states={};zero_checks=[]
    for variant in ('head-continuation','last-block-lora'):
        seed_scores=[]
        for seed in SEEDS:
            scores=np.zeros(count)
            for fold in folds:
                name=f'{method}-s{seed}-f{fold["fold"]}.pt';path=OUT/'nested-heads'/name
                assert sha(path)==first['states']['nested-heads/'+name]
                warm=torch.load(path,weights_only=True,map_location='cpu');torch.manual_seed(seed)
                if variant=='head-continuation':model=Head().cuda();model.load_state_dict(warm)
                else:
                    model=new_model(seed,warm)
                    ids=fold['fit'][:2]
                    with torch.inference_mode():
                        expected=model.head(x[ids],mask[ids],method)[0]
                        actual=model(torch.from_numpy(np.array(prefixes[ids])).cuda(),seqmask[ids],method)[0]
                    error=float((expected-actual).abs().max());assert error<1e-4
                    zero_checks.append(dict(seed=seed,fold=fold['fold'],zero_adapter_logit_max_error=error))
                params=[p for p in model.parameters() if p.requires_grad];optimizer=torch.optim.AdamW(params,lr=.001,weight_decay=.01)
                rng=np.random.default_rng(seed);history=[];torch.cuda.synchronize();start=time.perf_counter()
                for epoch in range(20):
                    losses=[];order=rng.permutation(fold['fit'])
                    for offset in range(0,len(order),8):
                        ids=order[offset:offset+8].tolist();optimizer.zero_grad()
                        if variant=='head-continuation':logits,pooled=model(x[ids],mask[ids],method)
                        else:logits,pooled=model(torch.from_numpy(np.array(prefixes[ids])).cuda(),seqmask[ids],method)
                        loss=objective(logits,pooled,y[ids],fine[ids],method);loss.backward();optimizer.step();losses.append(float(loss.detach()))
                    if epoch in (0,9,19):history.append(dict(epoch=epoch+1,mean_batch_loss=float(np.mean(losses))))
                model.eval();torch.cuda.synchronize();train_seconds=time.perf_counter()-start;ev=time.perf_counter()
                with torch.inference_mode():
                    for offset in range(0,len(fold['test']),8):
                        ids=fold['test'][offset:offset+8]
                        if variant=='head-continuation':logits,_=model(x[ids],mask[ids],method)
                        else:logits,_=model(torch.from_numpy(np.array(prefixes[ids])).cuda(),seqmask[ids],method)
                        scores[ids]=(1-logits.sigmoid()).cpu().numpy()
                torch.cuda.synchronize();eval_seconds=time.perf_counter()-ev
                state=state_trainable(model);path=OUT/'adapters'/f'{variant}-s{seed}-f{fold["fold"]}.pt';torch.save(state,path)
                states[path.relative_to(OUT).as_posix()]=sha(path)
                histories.append(dict(variant=variant,architecture=method,seed=seed,fold=fold['fold'],train_seconds=train_seconds,
                    cached_eval_seconds=eval_seconds,eval_count=len(fold['test']),trainable_parameters=sum(p.numel() for p in params),loss=history))
                print(variant,seed,fold['fold'],f'{train_seconds:.1f}s',f'loss {history[-1]["mean_batch_loss"]:.4f}',flush=True)
                del model,optimizer,params;torch.cuda.empty_cache()
            seed_scores.append(scores)
        scores=np.stack(seed_scores);np.save(OUT/f'stage2-{variant}-scores.npy',scores)
        summaries[variant],outputs[variant]=summarize(scores,rows,guards,challenge)
        print('RESULT',variant,summaries[variant],flush=True)
        write(OUT/'stage2-progress.json',dict(completed=summaries,history=histories))
    write(OUT/'stage2-summary.json',summaries);write(OUT/'stage2-predictions.json',outputs);write(OUT/'stage2-training.json',histories)
    write(OUT/'stage2-lock.json',dict(architecture=method,states=states,zero_adapter_checks=zero_checks,
        code_sha256=sha(ROOT/'tools/local_mark_adapt.py'),nested_lock_sha256=sha(OUT/'nested-lock.json'),seconds=time.perf_counter()-startall,
        torch=torch.__version__,device=torch.cuda.get_device_name(),peak_allocated_gpu_mb=torch.cuda.max_memory_allocated()/2**20))


if __name__=='__main__':main()
