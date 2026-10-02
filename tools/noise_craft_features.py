"""Fixed learned representation comparison; reuses the original frozen CRAFT encoder.

Training labels are the original development set only. Newer annotations are now
reused diagnostics: their images were inspected for the earlier HOG experiment.
No production model or worker is changed. Run using the existing GPU runtime.
"""
import hashlib
import json
import statistics
import time
from pathlib import Path

import cv2
import numpy as np
import torch
from PIL import Image
from easyocr.detection import get_detector
from easyocr.imgproc import normalizeMeanVariance

import noise_verifier_trial as trial

OUT=trial.OUT
WEIGHTS=trial.ROOT/'data/model-trials/models/easyocr/craft_mlt_25k.pth'


def main():
    if (OUT/'craft-features.npz').exists(): raise RuntimeError('Keep frozen representation')
    torch.set_num_threads(2)
    rows=trial.read(OUT/'dataset.json')
    config=dict(weights_sha256=trial.digest(WEIGHTS),code_sha256=trial.digest(__file__),
                dataset_sha256=trial.digest(OUT/'dataset.json'),side=192,pool=4,
                method='Frozen CRAFT shared feature map, 4x4 adaptive mean pool, normalized candidate ROI; equal normalized ROI+context comparison',
                labels='Original development only; newer-annotation pixels already inspected, therefore reused validation',
                threshold='Same fixed spatial OOF max-protected + .05 and optional .8 distance-ratio guard')
    trial.write('craft-contract.json',config)
    t=time.perf_counter(); model=get_detector(str(WEIGHTS),device='cuda')
    model.eval(); torch.cuda.synchronize(); init_ms=(time.perf_counter()-t)*1000
    arrays={'craft-mark':[],'craft-context':[]}; times=[]
    for r in rows:
        path=OUT/r['crop']; assert trial.digest(path)==r['sha256']
        im=np.asarray(Image.open(path).convert('RGB'))
        box=np.array(r['crop_box'])*192/np.array([im.shape[1],im.shape[0],im.shape[1],im.shape[0]])
        torch.cuda.synchronize(); start=time.perf_counter()
        im=cv2.resize(im,(192,192),interpolation=cv2.INTER_AREA)
        x=torch.from_numpy(normalizeMeanVariance(im).transpose(2,0,1)[None]).cuda()
        with torch.inference_mode():
            _,feat=model(x)
            a,b,c,d=box/2
            roi=feat[:,:,max(0,int(b)-2):min(feat.shape[2],int(np.ceil(d))+2),max(0,int(a)-2):min(feat.shape[3],int(np.ceil(c))+2)]
            v=torch.nn.functional.adaptive_avg_pool2d(roi,(4,4)).flatten().cpu().numpy()
            context=torch.nn.functional.adaptive_avg_pool2d(feat,(4,4)).flatten().cpu().numpy()
        v=v/max(1e-8,np.linalg.norm(v)); context=context/max(1e-8,np.linalg.norm(context))
        arrays['craft-mark'].append(v); arrays['craft-context'].append(np.concatenate([v,context])/np.sqrt(2))
        torch.cuda.synchronize(); times.append((time.perf_counter()-start)*1000)
    np.savez_compressed(OUT/'craft-features.npz',**{k:np.stack(v) for k,v in arrays.items()})
    trial.write('craft-feature-timing.json',dict(init_ms=init_ms,unit='ms / crop both representations',mean=statistics.mean(times),median=statistics.median(times),p95=float(np.percentile(times,95)),maximum=max(times),raw=times,excludes='PNG decoding, disk I/O and model fit',torch=torch.__version__,numpy=np.__version__,opencv=cv2.__version__,device=torch.cuda.get_device_name(),peak_allocated_mb=torch.cuda.max_memory_allocated()/2**20))
    print(json.dumps(config),flush=True)


if __name__=='__main__': main()
