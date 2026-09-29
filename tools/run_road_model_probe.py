"""Bounded, unadapted historical-road model trial. No OSM or reference labels as input."""
import hashlib, json, sys, time
from pathlib import Path
import numpy as np
from PIL import Image
import torch

ROOT=Path(__file__).resolve().parents[1]
MODEL=ROOT/'data/trail-model'
SOURCE=ROOT/'evidence/trail-round4/vendor'
sys.path.insert(0,str(SOURCE))
from models import Resnet18_Unet_Big_Attention

def main():
    out=ROOT/'evidence/trail-round4'
    target=out/'road-model-v1.json'
    if target.exists(): raise RuntimeError('Preserve prior run')
    weights=MODEL/'road-resnet18.pt'
    digest=hashlib.sha256(weights.read_bytes()).hexdigest()
    assert digest=='759969dc4a053a8bac9214df54fab3f6f0e6731b9c438371f838e90b344e7b81'
    assert torch.cuda.is_available(), 'GPU trial requires CUDA'
    torch.set_num_threads(2)
    model=Resnet18_Unet_Big_Attention(1,imagenet1k=False).eval()
    checkpoint=torch.load(weights,map_location='cpu',weights_only=True)
    model.load_state_dict(checkpoint,strict=True)
    model=model.cuda()
    rows=[]
    for scene in json.loads((out/'inputs.json').read_text())['scenes']:
        path=out/scene['path']
        assert hashlib.sha256(path.read_bytes()).hexdigest()==scene['sha256']
        im=Image.open(path).convert('RGB');pixels=np.asarray(im)
        h,w=pixels.shape[:2];probs=np.zeros((h,w),np.float32);counts=np.zeros_like(probs)
        xs=sorted(set(list(range(0,w-511,384))+[w-512]))
        ys=sorted(set(list(range(0,h-511,384))+[h-512]))
        torch.cuda.reset_peak_memory_stats();torch.cuda.synchronize();start=time.perf_counter()
        with torch.inference_mode():
            for y in ys:
                for x in xs:
                    batch=torch.from_numpy(pixels[y:y+512,x:x+512].copy()).permute(2,0,1).unsqueeze(0).float().cuda()/255
                    p=model(batch).sigmoid()[0,0].cpu().numpy()
                    probs[y:y+512,x:x+512]+=p;counts[y:y+512,x:x+512]+=1
        torch.cuda.synchronize();seconds=time.perf_counter()-start
        probs/=counts
        np.save(out/(scene['id']+'-road-prob.npy'),probs)
        Image.fromarray((probs*255).astype('uint8')).save(out/(scene['id']+'-road-prob.png'))
        overlay=pixels.copy().astype(float);mask=probs>=.5
        overlay[mask]=.4*overlay[mask]+.6*np.array([235,35,95])
        Image.fromarray(overlay.astype('uint8')).save(out/(scene['id']+'-road-model.png'))
        row=dict(scene=scene['id'],seconds=seconds,peak_allocated_mb=torch.cuda.max_memory_allocated()/2**20,
                 peak_reserved_mb=torch.cuda.max_memory_reserved()/2**20,above_half_pixels=int(mask.sum()),patches=len(xs)*len(ys))
        rows.append(row);print(json.dumps(row),flush=True)
    target.write_text(json.dumps(dict(device=torch.cuda.get_device_name(),torch=torch.__version__,checkpoint_sha256=digest,
        model_source_sha256=hashlib.sha256((SOURCE/'models.py').read_bytes()).hexdigest(),runs=rows),indent=2))

if __name__=='__main__':main()
