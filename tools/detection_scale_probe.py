"""Pixel-only CRAFT scale experiment; references never enter this process."""
import argparse, hashlib, json, sys, time
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
import cv2
import numpy as np
import torch
from PIL import Image
from easyocr.detection import get_detector
from easyocr.imgproc import resize_aspect_ratio,normalizeMeanVariance
from mapwalker.angled import rotate_with_transform
from mapwalker.region_model import deduplicate

def detect(engine,image,scale):
    proposals=[];passes=[]
    for angle in (0,-45,45,90,180,270):
        tick=time.perf_counter()
        rotated,transform=rotate_with_transform(image,angle)
        scaled=rotated.resize((round(rotated.width*scale),round(rotated.height*scale)))
        inverse=cv2.invertAffineTransform(transform)
        resized,ratio,_=resize_aspect_ratio(np.asarray(scaled),1536,cv2.INTER_LINEAR,1)
        x=torch.from_numpy(normalizeMeanVariance(resized).transpose(2,0,1)[None]).cuda()
        with torch.inference_mode():y,_=engine(x)
        score=y[0,:,:,0].cpu().numpy()
        count,labels,stats,_=cv2.connectedComponentsWithStats((score>=.20).astype('uint8'),8)
        factor=2/ratio/scale;ps=[]
        for i,(rx,ry,w,h,area) in enumerate(stats[1:],1):
            peak=float(score[labels==i].max())
            if area<5 or peak<.30:continue
            x0=max(0,float(rx*factor)-6);y0=max(0,float(ry*factor)-6)
            x1=min(rotated.width,float((rx+w)*factor)+6);y1=min(rotated.height,float((ry+h)*factor)+6)
            a=np.array([[x0,y0,1],[x1,y0,1],[x1,y1,1],[x0,y1,1]])@inverse.T
            ps.append(dict(kind='text',text='',box=[float(a[:,0].min()),float(a[:,1].min()),float(a[:,0].max()),float(a[:,1].max())],score=peak,repeating=False,details=dict(angle_degrees_ccw=angle,scale=scale,core_area=int(area))))
        del x,y;torch.cuda.empty_cache()
        passes.append(dict(angle=angle,ms=(time.perf_counter()-tick)*1000,proposals=ps));proposals+=ps
    return dict(proposals=deduplicate(proposals),passes=passes,total_inference_ms=sum(p['ms'] for p in passes))

def main():
    parser=argparse.ArgumentParser();parser.add_argument('--scale',type=float,required=True);parser.add_argument('--manifest',default='evidence/symbol-first/inputs.json');parser.add_argument('--out',required=True);args=parser.parse_args()
    out=Path(args.out)
    if out.exists():raise RuntimeError('Preserve previous outputs')
    weights=ROOT/'data/model-trials/models/easyocr/craft_mlt_25k.pth'
    torch.set_num_threads(2);torch.cuda.reset_peak_memory_stats();tick=time.perf_counter()
    engine=get_detector(str(weights),device='cuda');init_ms=(time.perf_counter()-tick)*1000
    manifest=Path(args.manifest);suite=json.loads(manifest.read_text('utf-8'))
    for scene in suite['scenes']:
        path=manifest.parent/scene['path'];assert hashlib.sha256(path.read_bytes()).hexdigest()==scene['sha256']
        tick=time.perf_counter();image=Image.open(path).convert('RGB');decode_ms=(time.perf_counter()-tick)*1000
        row=dict(scene=scene['id'],decode_ms=decode_ms,**detect(engine,image,args.scale))
        with out.open('a',encoding='utf-8') as f:f.write(json.dumps(row)+'\n')
        print(scene['id'],len(row['proposals']),round(row['total_inference_ms']),flush=True)
    out.with_suffix('.meta.json').write_text(json.dumps(dict(scale=args.scale,init_ms=init_ms,peak_allocated_mib=torch.cuda.max_memory_allocated()/1024**2,weights_sha256=hashlib.sha256(weights.read_bytes()).hexdigest(),harness_sha256=hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),inputs_sha256=hashlib.sha256(manifest.read_bytes()).hexdigest(),gpu=torch.cuda.get_device_name(0)),indent=2),'utf-8')
if __name__=='__main__':main()
