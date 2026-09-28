"""Pixel-only proposals. Never reads references or evaluation outcomes."""
import argparse,json,sys,time,hashlib,threading,subprocess
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
import cv2,numpy as np
from PIL import Image
from mapwalker.detectors import CONFIG,symbol_proposals
from mapwalker.junctions import junction_proposals
from mapwalker.trails import trail_proposals
from mapwalker.angled import rotate_with_transform
from run_symbol_first import deduplicate
OUT=ROOT/'evidence/detection-round2'
def main():
 parser=argparse.ArgumentParser();parser.add_argument('method',choices=['symbols-base','symbols-dark','trails-base','trails-dark','craft-base','craft-scale3']);parser.add_argument('--split',choices=['development','fresh','holdout'],required=True);args=parser.parse_args()
 stem=args.method+'-'+args.split;target=OUT/(stem+'.jsonl')
 if target.exists():raise RuntimeError('Preserve existing results')
 input_manifest=OUT/('holdout-inputs.json' if args.split=='holdout' else 'inputs.json');suite=json.loads(input_manifest.read_text('utf-8'));scenes=[s for s in suite['scenes'] if s['split']==args.split]
 (OUT/(stem+'-harness.py')).write_bytes(Path(__file__).read_bytes())
 meta=dict(method=args.method,split=args.split,inputs_sha256=hashlib.sha256(input_manifest.read_bytes()).hexdigest(),code={p.name:hashlib.sha256(p.read_bytes()).hexdigest() for p in [Path(__file__),ROOT/'mapwalker/detectors.py',ROOT/'mapwalker/trails.py',ROOT/'mapwalker/junctions.py',ROOT/'mapwalker/angled.py',ROOT/'tools/run_symbol_first.py']},status='running')
 samples=[];stop=threading.Event()
 def monitor():
  while not stop.wait(.7):
   try:samples.append(float(subprocess.check_output(['nvidia-smi','--query-gpu=memory.used','--format=csv,noheader,nounits'],text=True,creationflags=0x08000000).strip()))
   except Exception:pass
 thread=threading.Thread(target=monitor,daemon=True);thread.start();torch=None;tick=time.perf_counter()
 try:
  neural=args.method.startswith('craft');scale=3 if args.method=='craft-scale3' else 2
  if neural:
   import torch
   from easyocr.detection import get_detector
   from easyocr.imgproc import resize_aspect_ratio,normalizeMeanVariance
   assert torch.cuda.is_available();torch.set_num_threads(2);torch.cuda.reset_peak_memory_stats()
   weights=ROOT/'data/model-trials/models/easyocr/craft_mlt_25k.pth'
   engine=get_detector(str(weights),device='cuda');meta.update(weights_sha256=hashlib.sha256(weights.read_bytes()).hexdigest(),gpu=torch.cuda.get_device_name(0),scale=scale)
  meta['init_ms']=(time.perf_counter()-tick)*1000
  config={**CONFIG,'ink_threshold':110 if args.method.endswith('dark') else 135};meta['config']=config
  for scene in scenes:
   path=OUT/scene['path'];assert hashlib.sha256(path.read_bytes()).hexdigest()==scene['sha256']
   tick=time.perf_counter();image=Image.open(path).convert('RGB');decode_ms=(time.perf_counter()-tick)*1000
   proposals=[];passes=[]
   for angle in suite['angles'] if neural else [0]:
    tick=time.perf_counter()
    if neural:
     rotated,transform=rotate_with_transform(image,angle);scaled=rotated.resize((rotated.width*scale,rotated.height*scale));inverse=cv2.invertAffineTransform(transform)
     resized,ratio,_=resize_aspect_ratio(np.asarray(scaled),1536,cv2.INTER_LINEAR,1)
     x=torch.from_numpy(normalizeMeanVariance(resized).transpose(2,0,1)[None]).cuda();torch.cuda.synchronize()
    prep=(time.perf_counter()-tick)*1000;tick=time.perf_counter()
    if args.method.startswith('symbols'):ps=symbol_proposals(image,config)+junction_proposals(image,config)
    elif args.method.startswith('trails'):ps=trail_proposals(image,config)
    else:
     with torch.inference_mode():y,_=engine(x)
     score=y[0,:,:,0].cpu().numpy();count,labels,stats,_=cv2.connectedComponentsWithStats((score>=.20).astype('uint8'),8);ps=[];factor=2/ratio/scale
     for i,(rx,ry,w,h,area) in enumerate(stats[1:],1):
      peak=float(score[labels==i].max())
      if area<5 or peak<.30:continue
      x0=max(0,float(rx*factor)-6);y0=max(0,float(ry*factor)-6);x1=min(rotated.width,float((rx+w)*factor)+6);y1=min(rotated.height,float((ry+h)*factor)+6)
      a=np.array([[x0,y0,1],[x1,y0,1],[x1,y1,1],[x0,y1,1]])@inverse.T
      ps.append(dict(kind='text',text='',box=[float(a[:,0].min()),float(a[:,1].min()),float(a[:,0].max()),float(a[:,1].max())],polygon=a.tolist(),score=peak,repeating=False,details=dict(method='character region; unread',angle=angle)))
     torch.cuda.synchronize()
    elapsed=(time.perf_counter()-tick)*1000;passes.append(dict(angle=angle,prepare_ms=prep,detect_ms=elapsed,proposals=ps));proposals.extend(ps)
   tick=time.perf_counter();unique=deduplicate(proposals) if neural else proposals;post=(time.perf_counter()-tick)*1000
   row=dict(scene=scene['id'],passes=passes,proposals=unique,decode_ms=decode_ms,post_ms=post,total_inference_ms=sum(p['prepare_ms']+p['detect_ms'] for p in passes)+post)
   with target.open('a',encoding='utf-8') as f:f.write(json.dumps(row,ensure_ascii=False)+'\n')
   print(stem,scene['id'],len(unique),round(row['total_inference_ms']),flush=True)
  meta['status']='complete'
 finally:
  stop.set();thread.join(2);meta['gpu_total_peak_mib']=max(samples,default=None)
  if torch:meta['torch_peak_allocated_mib']=torch.cuda.max_memory_allocated()/1024**2
  (OUT/(stem+'-run.json')).write_text(json.dumps(meta,indent=2),'utf-8')
if __name__=='__main__':
 sys.stdout.reconfigure(encoding='utf-8');main()
