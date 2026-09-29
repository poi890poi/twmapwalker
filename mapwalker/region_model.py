"""Isolated local CRAFT inference. Optional torch/easyocr runtime; no OCR or references."""
import argparse
import base64
import hashlib
import importlib.metadata
import io
import json
import sys
import time
from pathlib import Path

def iou(a,b):
    overlap=max(0,min(a[2],b[2])-max(a[0],b[0]))*max(0,min(a[3],b[3])-max(a[1],b[1]))
    return overlap/max(1,(a[2]-a[0])*(a[3]-a[1])+(b[2]-b[0])*(b[3]-b[1])-overlap)

def deduplicate(items):
    kept=[]
    for p in sorted(items,key=lambda p:p['score'],reverse=True):
        if not any(iou(p['box'],q['box'])>=.4 for q in kept):
            kept.append(p)
    return kept

def compact_additions(base,large):
    additions=[]
    for p in large:
        x,y,x1,y1=p['box']
        if p['score']<.5 or max(x1-x,y1-y)>96:
            continue
        if any(iou(p['box'],q['box'])>=.25 for q in base):
            continue
        additions.append(p)
    return base+deduplicate(additions)

class RegionModel:
    def __init__(self, weights, profile='craft-original'):
        import torch
        from easyocr.detection import get_detector
        if not torch.cuda.is_available():
            raise RuntimeError('Text-region detector requires its configured CUDA runtime')
        torch.set_num_threads(2)
        if profile not in ('craft-original','synthetic-map-v1'):
            raise ValueError('Unknown text-region profile')
        self.profile=profile
        self.engine=get_detector(str(weights),device='cuda')

    def __call__(self,image):
        import cv2
        import numpy as np
        import torch
        from easyocr.imgproc import resize_aspect_ratio,normalizeMeanVariance
        from .angled import rotate_with_transform
        scales=[];all_proposals=[]
        for scale in (2,3):
            proposals=[]
            for angle in (0,-45,45,90,180,270):
                rotated,transform=rotate_with_transform(image,angle)
                scaled=rotated.resize((rotated.width*scale,rotated.height*scale))
                inverse=cv2.invertAffineTransform(transform)
                resized,ratio,_=resize_aspect_ratio(np.asarray(scaled),1536,cv2.INTER_LINEAR,1)
                x=torch.from_numpy(normalizeMeanVariance(resized).transpose(2,0,1)[None]).cuda()
                with torch.inference_mode():
                    y,_=self.engine(x)
                score=y[0,:,:,0].cpu().numpy()
                count,labels,stats,_=cv2.connectedComponentsWithStats((score>=.20).astype('uint8'),8)
                factor=2/ratio/scale
                for i,(rx,ry,w,h,area) in enumerate(stats[1:],1):
                    peak=float(score[labels==i].max())
                    if area<5 or peak<.30:
                        continue
                    x0=max(0,float(rx*factor)-6);y0=max(0,float(ry*factor)-6)
                    x1=min(rotated.width,float((rx+w)*factor)+6);y1=min(rotated.height,float((ry+h)*factor)+6)
                    a=np.array([[x0,y0,1],[x1,y0,1],[x1,y1,1],[x0,y1,1]])@inverse.T
                    proposals.append(dict(kind='text',text='',box=[float(a[:,0].min()),float(a[:,1].min()),float(a[:,0].max()),float(a[:,1].max())],score=peak,repeating=False,
                        details=dict(method='CRAFT unread character region',recognition='not attempted',angle_degrees_ccw=angle,scale=scale,polygon=a.tolist(),reading_candidates=[],score_meaning='Character-region activation; not transcription or POI probability')))
                # Different rotation sizes otherwise accumulate reserved CUDA blocks.
                # Outputs already live on CPU; release only unused device storage.
                del x,y
                torch.cuda.empty_cache()
            if self.profile=='synthetic-map-v1':
                all_proposals.extend(proposals)
            scales.append(deduplicate(proposals))
        torch.cuda.synchronize()
        output=compact_additions(*scales)
        if self.profile=='synthetic-map-v1':
            from .mark_policy import mark_regions
            output=mark_regions(output,all_proposals)
        return output

def main():
    from PIL import Image
    parser=argparse.ArgumentParser();parser.add_argument('--weights',required=True);parser.add_argument('--sha256',required=True);parser.add_argument('--packages',required=True);parser.add_argument('--profile',choices=['craft-original','synthetic-map-v1'],default='craft-original');args=parser.parse_args()
    start=time.perf_counter()
    if hashlib.sha256(Path(args.weights).read_bytes()).hexdigest()!=args.sha256:
        raise RuntimeError('Text-region weights changed; re-register before running')
    for name,version in json.loads(args.packages).items():
        if importlib.metadata.version(name)!=version:
            raise RuntimeError(f'Text-region runtime changed: {name}; re-register before running')
    model=RegionModel(args.weights,args.profile);init_ms=(time.perf_counter()-start)*1000
    tick=time.perf_counter();image=Image.open(io.BytesIO(base64.b64decode(sys.stdin.buffer.read(),validate=True))).convert('RGB')
    if image.size!=(384,384):
        raise ValueError('Expected a native tile with 64px halo')
    decode_ms=(time.perf_counter()-tick)*1000;tick=time.perf_counter();proposals=model(image);detect_ms=(time.perf_counter()-tick)*1000
    print(json.dumps(dict(proposals=proposals,timing=dict(model_init_ms=init_ms,decode_ms=decode_ms,detect_ms=detect_ms))))

if __name__=='__main__':
    main()
