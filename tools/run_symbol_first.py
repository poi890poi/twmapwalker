"""Pixel-only region experiments. This module never reads evaluation references."""
import os,sys,json,time,hashlib,argparse,traceback,threading,subprocess
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
OUT=ROOT/'evidence/symbol-first';DATA=ROOT/'data/model-trials';MODELS=DATA/'models'
for k,v in {'HF_HOME':DATA/'hf','TORCH_HOME':DATA/'torch','YOLO_CONFIG_DIR':DATA/'yolo','XDG_CACHE_HOME':DATA/'cache'}.items():
 v.mkdir(parents=True,exist_ok=True);os.environ[k]=str(v)
import numpy as np
import cv2
from PIL import Image
from mapwalker.angled import rotate_with_transform
from mapwalker.detectors import symbol_proposals,CONFIG
from mapwalker.junctions import junction_proposals

def iou(a,b):
 intersection=max(0,min(a[2],b[2])-max(a[0],b[0]))*max(0,min(a[3],b[3])-max(a[1],b[1]))
 return intersection/max(1,(a[2]-a[0])*(a[3]-a[1])+(b[2]-b[0])*(b[3]-b[1])-intersection)

def deduplicate(items,threshold=.40):
 out=[]
 for p in sorted(items,key=lambda p:p['score'],reverse=True):
  if not any(iou(p['box'],q['box'])>=threshold for q in out):out.append(p)
 return out

def stable_ink(image):
 gray=cv2.cvtColor(np.asarray(image),cv2.COLOR_RGB2GRAY);all_regions=[]
 for threshold in range(70,171,10):
  _,labels,stats,_=cv2.connectedComponentsWithStats((gray<threshold).astype('uint8'),8)
  for x,y,w,h,area in stats[1:]:
   if not (12<=area<=3000 and min(w,h)>=6 and max(w,h)<=90 and max(w,h)/min(w,h)<=4 and .06<=area/(w*h)<=.85):continue
   all_regions.append(dict(box=[int(x),int(y),int(x+w),int(y+h)],threshold=threshold,area=int(area)))
 for p in all_regions:
  supporting={q['threshold'] for q in all_regions if iou(p['box'],q['box'])>=.60}
  p.update(score=len(supporting)/11,support=sorted(supporting),repeating=False,method='stable dark component')
 out=deduplicate([p for p in all_regions if len(p['support'])>=3])
 # Flag repeated shapes for review, without asserting that a repeated glyph is vegetation.
 signatures=[]
 for p in out:
  x,y,x1,y1=p['box'];crop=(gray[y:y1,x:x1]<p['threshold']).astype('uint8');h,w=crop.shape
  square=np.zeros((max(h,w),)*2,'uint8');square[(len(square)-h)//2:(len(square)+h)//2,(len(square)-w)//2:(len(square)+w)//2]=crop
  signatures.append(cv2.resize(square,(20,20),interpolation=cv2.INTER_AREA).astype(bool))
 for index,p in enumerate(out):
  a=signatures[index];area=(p['box'][2]-p['box'][0])*(p['box'][3]-p['box'][1]);peers=0
  for q,b in zip(out,signatures):
   other=(q['box'][2]-q['box'][0])*(q['box'][3]-q['box'][1])
   if .65<=area/other<=1.54 and (a&b).sum()/max(1,(a|b).sum())>=.87:peers+=1
  p.update(similar_components=peers,repeating=peers>=4)
 return out

def main():
 parser=argparse.ArgumentParser();parser.add_argument('model',choices=['baseline-symbols','ppocr-det','craft-char','stable-ink']);parser.add_argument('--development-only',action='store_true');args=parser.parse_args()
 target=OUT/(args.model+'.jsonl')
 if target.exists():raise RuntimeError('Preserve existing run before retrying')
 suite=json.loads((OUT/'inputs.json').read_text('utf-8'));scenes=suite['scenes']
 if args.development_only:scenes=[s for s in scenes if s['split']=='previous-development']
 meta=dict(model=args.model,inputs_sha256=hashlib.sha256((OUT/'inputs.json').read_bytes()).hexdigest(),harness_sha256=hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),started=time.time(),status='running',rows=0)
 (OUT/(args.model+'-harness.py')).write_bytes(Path(__file__).read_bytes())
 samples=[];stop=threading.Event()
 def monitor():
  while not stop.wait(.5):
   try:samples.append(float(subprocess.check_output(['nvidia-smi','--query-gpu=memory.used','--format=csv,noheader,nounits'],text=True,creationflags=0x08000000).strip()))
   except Exception:pass
 thread=threading.Thread(target=monitor,daemon=True);thread.start();init=time.perf_counter();torch=None
 try:
  if args.model in ['ppocr-det','craft-char']:
   import torch
   assert torch.cuda.is_available(),'CUDA unavailable';torch.set_num_threads(2);torch.cuda.reset_peak_memory_stats();meta.update(gpu=torch.cuda.get_device_name(0),torch=torch.__version__)
  if args.model=='ppocr-det':
   import onnxruntime as ort
   ort.preload_dlls()
   from rapidocr import RapidOCR
   from omegaconf import OmegaConf
   engine=RapidOCR(params={'Global.text_score':0.0,'Global.use_cls':False,'EngineConfig.onnxruntime.use_cuda':True,'EngineConfig.onnxruntime.cuda_ep_cfg.cudnn_conv_algo_search':'HEURISTIC','Rec.rec_batch_num':1,'EngineConfig.onnxruntime.intra_op_num_threads':2,'EngineConfig.onnxruntime.inter_op_num_threads':1,'Global.model_root_dir':str(MODELS/'rapidocr')})
   meta['config']=OmegaConf.to_container(engine.cfg,resolve=True,enum_to_str=True);meta['actual_providers']=engine.text_det.session.session.get_providers();assert 'CUDAExecutionProvider' in meta['actual_providers']
   def detect(image):
    r=engine(np.asarray(image)[:,:,::-1],use_cls=False,use_rec=False)
    return [dict(polygon=b.tolist(),score=float(c),method='text detection only') for b,c in zip(r.boxes if r.boxes is not None else [],r.scores if r.scores is not None else [])]
  elif args.model=='craft-char':
   from easyocr.detection import get_detector
   from easyocr.imgproc import resize_aspect_ratio,normalizeMeanVariance
   engine=get_detector(str(MODELS/'easyocr/craft_mlt_25k.pth'),device='cuda')
   def detect(image):
    resized,ratio,_=resize_aspect_ratio(np.asarray(image),1536,cv2.INTER_LINEAR,1)
    x=torch.from_numpy(normalizeMeanVariance(resized).transpose(2,0,1)[None]).cuda()
    with torch.inference_mode():y,_=engine(x)
    score=y[0,:,:,0].cpu().numpy();count,labels,stats,_=cv2.connectedComponentsWithStats((score>=.20).astype('uint8'),8);out=[]
    factor=2/ratio
    for i,(x,y,w,h,area) in enumerate(stats[1:],1):
     peak=float(score[labels==i].max())
     if area<5 or peak<.30:continue
     # Input is 2x native, so 12 input pixels provide 6 native pixels of context.
     x0=max(0,float(x*factor)-12);y0=max(0,float(y*factor)-12);x1=min(image.width,float((x+w)*factor)+12);y1=min(image.height,float((y+h)*factor)+12)
     out.append(dict(polygon=[[x0,y0],[x1,y0],[x1,y1],[x0,y1]],score=peak,core_area=int(area),method='character region, no affinity grouping'))
    return out
  meta['init_ms']=(time.perf_counter()-init)*1000
  for scene in scenes:
   image=Image.open(OUT/scene['path']).convert('RGB');proposals=[];passes=[]
   for angle in suite['angles'] if torch else [0]:
    if torch:
     rotated,transform=rotate_with_transform(image,angle);scaled=rotated.resize((rotated.width*2,rotated.height*2));inverse=cv2.invertAffineTransform(transform);torch.cuda.synchronize()
    tick=time.perf_counter()
    if args.model=='baseline-symbols':ps=symbol_proposals(image)+junction_proposals(image,CONFIG)
    elif args.model=='stable-ink':ps=stable_ink(image)
    else:
     ps=detect(scaled);torch.cuda.synchronize()
     for p in ps:
      a=np.asarray(p['polygon'])/2;a=np.column_stack([a,np.ones(len(a))])@inverse.T
      p.update(polygon=a.tolist(),box=[float(a[:,0].min()),float(a[:,1].min()),float(a[:,0].max()),float(a[:,1].max())],repeating=False)
    elapsed=(time.perf_counter()-tick)*1000
    for p in ps:p['angle']=angle
    proposals.extend(ps);passes.append(dict(angle=angle,ms=elapsed,proposals=ps))
   unique=deduplicate(proposals)
   row=dict(scene=scene['id'],passes=passes,proposals=unique,total_inference_ms=sum(p['ms'] for p in passes))
   with target.open('a',encoding='utf-8') as f:f.write(json.dumps(row,ensure_ascii=False)+'\n')
   meta['rows']+=1;print(args.model,scene['id'],len(unique),round(row['total_inference_ms']),flush=True)
  meta['status']='complete'
 except Exception as e:
  meta.update(status='error',error=str(e),traceback=traceback.format_exc());print(meta['traceback'],flush=True)
 finally:
  stop.set();thread.join(2);meta.update(total_seconds=time.perf_counter()-init,gpu_total_peak_mib=max(samples,default=None),gpu_samples_mib=samples)
  if torch:meta['torch_peak_allocated_mib']=torch.cuda.max_memory_allocated()/1024**2
  (OUT/(args.model+'-run.json')).write_text(json.dumps(meta,ensure_ascii=False,indent=2),'utf-8')
if __name__=='__main__':
 sys.stdout.reconfigure(encoding='utf-8');main()
