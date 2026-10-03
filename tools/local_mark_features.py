"""All target tokens and lossless frozen-prefix cache for paired last-block tuning."""
import math
import time
import numpy as np
import torch
from PIL import Image
from transformers import AutoModel
from .contour_learner_data import ROOT,read,write,sha
from .noise_methods_features import WEIGHTS,native_window
from .local_mark_data import OUT,CACHE


def encode(rows,name):
    torch.set_num_threads(2);torch.manual_seed(7)
    model=AutoModel.from_pretrained(str(WEIGHTS),local_files_only=True).eval().cuda()
    prefix=np.lib.format.open_memmap(CACHE/f'{name}-prefix.npy',mode='w+',dtype=np.float32,shape=(len(rows),785,384))
    arrays={};times=[];replays=[];capture={}
    hook=model.encoder.layer[-1].register_forward_pre_hook(lambda module,args:capture.update(x=args[0].detach()))
    for i,r in enumerate(rows):
        path=ROOT/r['context'];assert sha(path)==r['context_sha256']
        with Image.open(path) as im:im,box=native_window(im.convert('RGB'),r['context_box'])
        pixels=np.asarray(im.resize((392,392),Image.Resampling.BICUBIC),np.float32)/255
        pixels=(pixels-np.array([.485,.456,.406],np.float32))/np.array([.229,.224,.225],np.float32)
        x=torch.from_numpy(pixels.transpose(2,0,1).copy()[None]).cuda()
        torch.cuda.synchronize();start=time.perf_counter()
        with torch.inference_mode():tokens=model(pixel_values=x).last_hidden_state[0]
        prefix[i]=capture['x'][0].cpu().numpy()
        a,b,c,d=np.array(box)*2/14
        x0,y0=max(0,min(27,math.floor(a))),max(0,min(27,math.floor(b)))
        x1,y1=max(x0+1,min(28,math.ceil(c))),max(y0+1,min(28,math.ceil(d)))
        indices=np.array([1+y*28+x for y in range(y0,y1) for x in range(x0,x1)],np.int64)
        arrays[f'i{i}']=indices;arrays[f'p{i}']=torch.nn.functional.normalize(tokens[indices],dim=-1).cpu().numpy()
        if i in (0,len(rows)-1):
            with torch.inference_mode():again=model.layernorm(model.encoder.layer[-1](torch.from_numpy(np.array(prefix[i:i+1])).cuda()))[0]
            error=float((again-tokens).abs().max());assert error<1e-5;replays.append(error)
        torch.cuda.synchronize();times.append((time.perf_counter()-start)*1000)
        if (i+1)%50==0:print(f'Encoded {i+1}/{len(rows)}',flush=True)
    hook.remove();prefix.flush();del prefix
    np.savez_compressed(OUT/f'{name}-features.npz',**arrays)
    write(OUT/f'{name}-feature-lock.json',dict(rows=[r['id'] for r in rows],code_sha256=sha(ROOT/'tools/local_mark_features.py'),
        arrays_sha256=sha(OUT/f'{name}-features.npz'),prefix_sha256=sha(CACHE/f'{name}-prefix.npy'),
        weights_sha256=sha(WEIGHTS/'model.safetensors'),feature_ms=times,prefix_replay_max_errors=replays,
        time_scope='GPU encoding, ROI selection and CPU prefix transfer; excludes decoding and image normalization; replay samples additionally include last-block verification',
        torch=torch.__version__,device=torch.cuda.get_device_name(),peak_allocated_mb=torch.cuda.max_memory_allocated()/2**20))
    print(name,'features ready; raw prefix stays in ignored data cache',flush=True)


def main():
    if (OUT/'development-feature-lock.json').exists():raise RuntimeError('Preserve frozen arrays')
    rows=read(OUT/'training.json')+read(OUT/'guards.json')+read(OUT/'challenge.json')
    encode(rows,'development')


if __name__=='__main__':main()
