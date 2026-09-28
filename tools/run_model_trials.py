"""Standalone model trials; outputs never publish to Mapwalker's production store."""
import os,sys,json,time,math,hashlib,traceback,argparse,subprocess,threading
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
DATA=ROOT/'data/model-trials';OUT=ROOT/'evidence/model-trials';MODELS=DATA/'models';MODELS.mkdir(exist_ok=True)
for key,value in {'HF_HOME':DATA/'hf','TORCH_HOME':DATA/'torch','YOLO_CONFIG_DIR':DATA/'yolo','XDG_CACHE_HOME':DATA/'cache'}.items():
 value.mkdir(parents=True,exist_ok=True);os.environ[key]=str(value)
os.environ['HF_HUB_DISABLE_SYMLINKS_WARNING']='1'
import numpy as np
import cv2
from PIL import Image
from mapwalker.angled import rotate_with_transform

def main():
 parser=argparse.ArgumentParser();parser.add_argument('model',choices=['baseline','ppocr6','craft','manga','dino','yolo']);parser.add_argument('--limit',type=int,default=0);args=parser.parse_args()
 suite=json.loads((OUT/'inputs.json').read_text('utf-8'));target=OUT/(args.model+'.jsonl')
 if target.exists():raise RuntimeError('Run already exists; preserve it before rerunning')
 rows=[];gpu_samples=[];stop=threading.Event()
 def monitor():
  while not stop.wait(.5):
   try:
    v=subprocess.check_output(['nvidia-smi','--query-gpu=memory.used','--format=csv,noheader,nounits'],creationflags=0x08000000,text=True).strip();gpu_samples.append(float(v))
   except Exception:pass
 t=threading.Thread(target=monitor,daemon=True);t.start()
 def save(row):
  rows.append(row)
  with target.open('a',encoding='utf-8') as f:f.write(json.dumps(row,ensure_ascii=False)+'\n')
  print(args.model,row.get('id'),row.get('angle'),row.get('text',''),len(row.get('proposals',row.get('predictions',[]))),flush=True)
 tic=time.perf_counter();metadata=dict(model=args.model,started=time.time(),inputs_sha256=hashlib.sha256((OUT/'inputs.json').read_bytes()).hexdigest(),script_sha256=hashlib.sha256(Path(__file__).read_bytes()).hexdigest())
 try:
  torch=None
  if args.model!='baseline':
   import torch
   torch.set_num_threads(2)
   if not torch.cuda.is_available():raise RuntimeError('CUDA unavailable; do not silently claim GPU trial')
   metadata.update(torch=torch.__version__,gpu=torch.cuda.get_device_name(0));torch.cuda.reset_peak_memory_stats()
  if args.model=='baseline':
   from rapidocr_onnxruntime import RapidOCR
   engine=RapidOCR(text_score=.45,intra_op_num_threads=2,inter_op_num_threads=1)
   def detect(im):
    result,_=engine(np.asarray(im)[:,:,::-1]);return [dict(polygon=p,text=s,score=float(c)) for p,s,c in (result or [])]
   def recognize(im):
    result,_=engine(np.asarray(im)[:,:,::-1],use_det=False,use_cls=False);return result
   metadata['provider']='CPUExecutionProvider'
  elif args.model=='ppocr6':
   import onnxruntime as ort
   ort.preload_dlls()
   from rapidocr import RapidOCR
   engine=RapidOCR(params={'Global.text_score':0.0,'Global.use_cls':False,'EngineConfig.onnxruntime.use_cuda':True,'EngineConfig.onnxruntime.cuda_ep_cfg.cudnn_conv_algo_search':'HEURISTIC','Rec.rec_batch_num':1,'EngineConfig.onnxruntime.intra_op_num_threads':2,'EngineConfig.onnxruntime.inter_op_num_threads':1,'Global.model_root_dir':str(MODELS/'rapidocr')})
   def detect(im):
    r=engine(np.asarray(im)[:,:,::-1],use_cls=False)
    return [dict(polygon=b.tolist(),text=s,score=float(c)) for b,s,c in zip(r.boxes if r.boxes is not None else [],r.txts if r.txts is not None else [],r.scores if r.scores is not None else [])]
   def recognize(im):
    r=engine(np.asarray(im)[:,:,::-1],use_det=False,use_cls=False);return [(str(a),float(b)) for a,b in zip(r.txts if r.txts is not None else [],r.scores if r.scores is not None else [])]
   metadata['available_providers']=ort.get_available_providers()
   metadata['actual_providers']={name:getattr(engine,name).session.session.get_providers() for name in ['text_det','text_rec']}
   if any('CUDAExecutionProvider' not in v for v in metadata['actual_providers'].values()):raise RuntimeError('CUDA fallback detected')
   from omegaconf import OmegaConf
   metadata['config']=OmegaConf.to_container(engine.cfg,resolve=True,enum_to_str=True)
  elif args.model=='craft':
   import easyocr
   engine=easyocr.Reader(['ja'],gpu=True,recognizer=False,model_storage_directory=str(MODELS/'easyocr'),user_network_directory=str(DATA/'easyocr-user'),verbose=False)
   def detect(im):
    horizontal,free=engine.detect(np.asarray(im),min_size=0,canvas_size=1536,mag_ratio=1)
    out=[]
    for x0,x1,y0,y1 in horizontal[0]:out.append(dict(polygon=[[int(x0),int(y0)],[int(x1),int(y0)],[int(x1),int(y1)],[int(x0),int(y1)]],text='',score=None))
    for p in free[0]:out.append(dict(polygon=np.asarray(p).tolist(),text='',score=None))
    return out
  elif args.model=='manga':
   from transformers import ViTImageProcessor,AutoTokenizer,VisionEncoderDecoderModel
   name=str(MODELS/'manga-ocr-base');processor=ViTImageProcessor.from_pretrained(name);tokenizer=AutoTokenizer.from_pretrained(name)
   engine=VisionEncoderDecoderModel.from_pretrained(name).eval().cuda()
   def recognize(im):
    pixels=processor(im.convert('L').convert('RGB'),return_tensors='pt').pixel_values.cuda()
    with torch.inference_mode():output=engine.generate(pixels,max_new_tokens=64)
    return tokenizer.decode(output[0],skip_special_tokens=True).replace(' ','')
  elif args.model=='dino':
   from transformers import AutoModel,AutoImageProcessor
   name=str(MODELS/'dinov2-small');processor=AutoImageProcessor.from_pretrained(name);engine=AutoModel.from_pretrained(name).eval().cuda()
   def features(im):
    a=np.asarray(im.resize((392,392))).astype('float32')/255
    a=(a-np.array(processor.image_mean))/np.array(processor.image_std)
    pixels=torch.from_numpy(a.astype('float32')).permute(2,0,1)[None].cuda()
    with torch.inference_mode():h=engine(pixel_values=pixels).last_hidden_state[:,1:]
    return torch.nn.functional.normalize(h[0],dim=-1)
  elif args.model=='yolo':
   from ultralytics import YOLOE
   from ultralytics.models.yolo.yoloe import YOLOEVPSegPredictor
   previous=os.getcwd();os.chdir(MODELS)
   try:engine=YOLOE('yoloe-26n-seg.pt')
   finally:os.chdir(previous)
   engine.to('cuda')
   metadata['reference_boxes']=[[259,110,288,144],[158,184,201,220]]
   metadata['reference_role']='development visual prompts; source-image responses are positive controls, not independent accuracy'

  metadata['init_ms']=(time.perf_counter()-tic)*1000
  (OUT/('harness-'+args.model+'.py')).write_text(Path(__file__).read_text('utf-8-sig'),'utf-8')
  if args.model in ['dino','yolo']:
   reference=Image.open(OUT/'inputs/JM50K_1924_new-symbols.png').convert('RGB')
   boxes=[[259,110,288,144],[158,184,201,220]]
   if args.model=='dino':
    prototypes=torch.stack([features(reference.crop(b)).mean(0) for b in boxes]);prototypes=torch.nn.functional.normalize(prototypes,dim=-1)
   for scene in suite['discovery']:
    im=Image.open(OUT/scene['path']).convert('RGB');torch.cuda.synchronize();tick=time.perf_counter()
    if args.model=='yolo':
     results=engine.predict(im,refer_image=reference,visual_prompts={'bboxes':np.array(boxes),'cls':np.array([0,1])},predictor=YOLOEVPSegPredictor,device=0,imgsz=768,verbose=False,save=False)
     torch.cuda.synchronize();elapsed=(time.perf_counter()-tick)*1000
     predictions=[dict(box=b.xyxy[0].cpu().tolist(),class_id=int(b.cls[0]),score=float(b.conf[0])) for b in results[0].boxes]
     save(dict(task='visual-prompt',id=scene['id'],ms=elapsed,predictions=predictions))
    else:
     h=features(im);similarity=h@h.T;similarity.fill_diagonal_(-1);novelty=1-similarity.topk(8,dim=1).values.mean(1);similar=h@prototypes.T
     torch.cuda.synchronize();elapsed=(time.perf_counter()-tick)*1000
     maps=dict(novelty=novelty.reshape(28,28).cpu().tolist(),school_similarity=similar[:,0].reshape(28,28).cpu().tolist(),spring_similarity=similar[:,1].reshape(28,28).cpu().tolist())
     save(dict(task='feature-exploration',id=scene['id'],ms=elapsed,maps=maps))
  if args.model in ['baseline','ppocr6','craft']:
   scenes=suite['discovery'][:args.limit or None]
   for scene in scenes:
    image=Image.open(OUT/scene['path']).convert('RGB')
    for angle in suite['angles']:
     rotated,transform=rotate_with_transform(image,angle);scaled=rotated.resize((rotated.width*2,rotated.height*2));inverse=cv2.invertAffineTransform(transform)
     if torch:torch.cuda.synchronize()
     tick=time.perf_counter();proposals=detect(scaled)
     if torch:torch.cuda.synchronize()
     elapsed=(time.perf_counter()-tick)*1000
     for p in proposals:
      points=np.asarray(p['polygon'],float)/2
      p['polygon']=(np.column_stack([points,np.ones(len(points))])@inverse.T).tolist()
     save(dict(task='discovery',id=scene['id'],angle=angle,ms=elapsed,proposals=proposals))
  if args.model in ['baseline','ppocr6','manga']:
   for crop in suite['recognition']:
    image=Image.open(OUT/crop['path']).convert('RGB')
    for angle in suite['angles']:
     rotated,_=rotate_with_transform(image,angle)
     if torch:torch.cuda.synchronize()
     tick=time.perf_counter();raw=recognize(rotated)
     if torch:torch.cuda.synchronize()
     save(dict(task='recognition-only',id=crop['id'],angle=angle,ms=(time.perf_counter()-tick)*1000,text=raw))
  metadata['status']='complete'
 except Exception as e:
  metadata.update(status='error',error=str(e),traceback=traceback.format_exc());print(metadata['traceback'],flush=True)
 finally:
  stop.set();t.join(2);metadata.update(total_seconds=time.perf_counter()-tic,rows=len(rows),gpu_total_peak_mib=max(gpu_samples,default=None),gpu_memory_samples_mib=gpu_samples)
  if torch is not None:
   metadata['torch_peak_allocated_mib']=torch.cuda.max_memory_allocated()/1024**2
  (OUT/(args.model+'-run.json')).write_text(json.dumps(metadata,ensure_ascii=False,indent=2),'utf-8')
if __name__=='__main__':
 sys.stdout.reconfigure(encoding='utf-8');main()
