"""Frozen native-scale DINO target descriptors for a problem-driven method survey."""
import math
import time
import numpy as np
from PIL import Image

from .contour_learner_data import ROOT,sha,read,write

OUT=ROOT/'evidence/noise-methods-survey'
BASE=ROOT/'evidence/contour-learner'
WEIGHTS=ROOT/'data/model-trials/models/dinov2-small'


def native_window(im,box):
    a,b,c,d=box;left=math.floor((a+c)/2)-98;top=math.floor((b+d)/2)-98
    rgb=np.asarray(im.convert('RGB'));fill=tuple(np.median(rgb.reshape(-1,3),axis=0).astype(int).tolist())
    window=Image.new('RGB',(196,196),fill)
    x0,y0=max(left,0),max(top,0);x1,y1=min(left+196,im.width),min(top+196,im.height)
    window.paste(im.crop((x0,y0,x1,y1)),(x0-left,y0-top))
    return window,[a-left,b-top,c-left,d-top]


def extract_rows(rows,model,torch):
    vectors=[];patches=[];telemetry=[]
    for i,row in enumerate(rows):
        path=ROOT/row['context'];assert sha(path)==row['context_sha256']
        with Image.open(path) as im:im,box=native_window(im.convert('RGB'),row['context_box'])
        torch.cuda.synchronize();start=time.perf_counter();pooled=[];target_patches=None
        for factor in (1,2):
            pixels=np.asarray(im.resize((196*factor,196*factor),Image.Resampling.BICUBIC),dtype=np.float32)/255
            pixels=(pixels-np.array([.485,.456,.406],np.float32))/np.array([.229,.224,.225],np.float32)
            x=torch.from_numpy(pixels.transpose(2,0,1).copy()[None]).cuda()
            with torch.inference_mode():tokens=model(pixel_values=x).last_hidden_state[0,1:]
            side=14*factor;grid=tokens.reshape(side,side,-1)
            a,b,c,d=np.array(box)*factor/14
            # Include every patch overlapping the target; retain native context and scale.
            x0,y0=max(0,min(side-1,math.floor(a))),max(0,min(side-1,math.floor(b)))
            x1,y1=max(x0+1,min(side,math.ceil(c))),max(y0+1,min(side,math.ceil(d)))
            region=grid[y0:y1,x0:x1].reshape(-1,384)
            pooled.append(torch.nn.functional.normalize(region.mean(0),dim=0).cpu().numpy())
            if factor==2:
                normalized=torch.nn.functional.normalize(region,dim=-1).cpu().numpy()
                take=np.unique(np.linspace(0,len(normalized)-1,min(64,len(normalized)),dtype=int))
                target_patches=normalized[take]
        vector=np.concatenate(pooled)/math.sqrt(2)
        torch.cuda.synchronize();elapsed=(time.perf_counter()-start)*1000
        vectors.append(vector);patches.append(target_patches)
        telemetry.append(dict(id=row['id'],feature_ms=elapsed,patches=len(target_patches)))
        if (i+1)%50==0:print(f'Encoded {i+1}/{len(rows)} targets',flush=True)
    return np.stack(vectors),patches,telemetry


def main():
    import torch
    from transformers import AutoModel
    OUT.mkdir(exist_ok=False)
    contract=dict(type='Offline survey and fixed pilots; no production suppression',
        problem='Small target amid overlapping structured ink; true POI loss costs more than retained clutter; appearance shifts between editions; few reliable labels.',
        inputs='Same 218 training and 58 reused protection crops; same buffered spatial folds. The 48 held-out targets remain unseen until a candidate qualifies.',
        methods=['DINO native ROI representation with unchanged RF + existing 18 structural features',
                 'DINO target nearest-example margin between contour and protected banks',
                 'One-class contour patch memory; preserve the most unusual 10% of target patches',
                 'One-class rank-16 affine subspace residual on DINO target descriptors',
                 'Within-image recurrence of native 8px and 16px ink patches, excluding the target region'],
        model='Existing local DINOv2-small weights, frozen; 196-native-pixel target-centered context at 1x and 2x; overlapping target tokens pooled; no per-target size normalization.',
        causal_inputs='Pixels and target geometry only. Labels fit/calibrate methods; geographic coordinates only split data. No OCR text or edition ID in prediction.',
        settings='Methods fixed before computing outputs. RF unchanged. kNN mean-three distances; patch-memory maximum 64 tokens/target, q90 distance; subspace rank16, exp(-residual^2/.1); recurrence q90 mismatch; calibration maximum protected OOF score + .025.',
        gate='At least 24/96 development contours caught, no flags on 58 protection probes, and more than 2/33 1924 hits. Qualifying methods ranked by 1924 hits then total hits; only the winner advances to frozen holdout. No threshold tuning there.',
        limits='Mechanism pilots inspired by literature, not reproductions of published benchmark systems. Research selection after previous experiments biases development results; fresh validation still needed. Unknown/repeated symbols remain protected.',
        weights_sha256=sha(WEIGHTS/'model.safetensors'),config_sha256=sha(WEIGHTS/'config.json'))
    write(OUT/'contract.json',contract)
    torch.set_num_threads(2);torch.manual_seed(7331)
    start=time.perf_counter();model=AutoModel.from_pretrained(str(WEIGHTS),local_files_only=True).eval().cuda()
    init_ms=(time.perf_counter()-start)*1000
    rows=read(BASE/'training.json');guards=read(BASE/'guards.json')
    x,patches,timing=extract_rows(rows+guards,model,torch)
    arrays=dict(vectors=x)
    arrays.update({f'p{i}':p for i,p in enumerate(patches)})
    np.savez_compressed(OUT/'dino-features.npz',**arrays)
    write(OUT/'feature-telemetry.json',dict(rows=timing,training_count=len(rows),guard_count=len(guards),
        initialization_ms=init_ms,excludes='Image decoding; includes tensor preprocessing, ROI pooling, both scales and GPU transfer/synchronization',
        torch=torch.__version__,device=torch.cuda.get_device_name(),peak_allocated_mb=torch.cuda.max_memory_allocated()/2**20))
    write(OUT/'feature-lock.json',dict(code_sha256=sha(ROOT/'tools/noise_methods_features.py'),
        arrays_sha256=sha(OUT/'dino-features.npz'),training_sha256=sha(BASE/'training.json'),
        guards_sha256=sha(BASE/'guards.json'),holdout_sha256=sha(BASE/'holdout-inputs.json')))
    print('Frozen target descriptors and local token banks ready. No held-out pixels used.',flush=True)


if __name__=='__main__':main()
