"""Change only raster representation before the existing pretrained detector."""
import argparse,hashlib,json,sys,time
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
import cv2,numpy as np,torch
from PIL import Image,ImageOps
from mapwalker.region_model import RegionModel

def simplify(image):
    gray=cv2.cvtColor(np.asarray(image),cv2.COLOR_RGB2GRAY)
    ink=(gray<135).astype('uint8')
    core=(cv2.distanceTransform(ink,cv2.DIST_L2,5)>=2).astype('uint8')
    restored=cv2.dilate(core,np.ones((3,3),'uint8'))&ink
    return Image.fromarray(np.repeat((255-restored*255)[:,:,None],3,axis=2))

def main():
    p=argparse.ArgumentParser();p.add_argument('--manifest',default='evidence/symbol-first/inputs.json');p.add_argument('--out',required=True);p.add_argument('--only');p.add_argument('--method',choices=['thick','contrast'],default='thick');args=p.parse_args()
    out=Path(args.out)
    if out.exists():raise RuntimeError('Preserve previous results')
    out.with_suffix('.harness.py').write_bytes(Path(__file__).read_bytes())
    weights=ROOT/'data/model-trials/models/easyocr/craft_mlt_25k.pth'
    torch.cuda.reset_peak_memory_stats();tick=time.perf_counter();model=RegionModel(weights);init_ms=(time.perf_counter()-tick)*1000
    manifest=Path(args.manifest)
    for s in json.loads(manifest.read_text('utf-8'))['scenes']:
        if args.only and s['id'] not in args.only.split(','):continue
        path=manifest.parent/s['path'];assert hashlib.sha256(path.read_bytes()).hexdigest()==s['sha256']
        im=Image.open(path).convert('RGB');tick=time.perf_counter();clean=simplify(im) if args.method=='thick' else ImageOps.autocontrast(im.convert('L'),cutoff=2).convert('RGB');pre_ms=(time.perf_counter()-tick)*1000
        clean.save(out.parent/(out.stem+'-'+s['id']+'.png'))
        tick=time.perf_counter();ps=model(clean);ms=(time.perf_counter()-tick)*1000
        row=dict(scene=s['id'],proposals=ps,preprocess_ms=pre_ms,total_inference_ms=ms)
        with out.open('a',encoding='utf-8') as f:f.write(json.dumps(row)+'\n')
        print(s['id'],len(ps),round(ms),flush=True)
    out.with_suffix('.meta.json').write_text(json.dumps(dict(init_ms=init_ms,peak_allocated_mib=torch.cuda.max_memory_allocated()/1024**2,weights_sha256=hashlib.sha256(weights.read_bytes()).hexdigest(),harness_sha256=hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),inputs_sha256=hashlib.sha256(manifest.read_bytes()).hexdigest()),indent=2),'utf-8')
if __name__=='__main__':main()
