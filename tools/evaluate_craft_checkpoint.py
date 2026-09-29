"""Pixel-only checkpoint comparison with unchanged production postprocessing."""
import argparse,hashlib,json,sys,time
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from PIL import Image
from mapwalker.region_model import RegionModel
import torch

def main():
    parser=argparse.ArgumentParser();parser.add_argument('--weights',required=True);parser.add_argument('--manifest',default='evidence/symbol-first/inputs.json');parser.add_argument('--out',required=True);parser.add_argument('--compact-core',action='store_true');parser.add_argument('--consensus',action='store_true');args=parser.parse_args()
    out=Path(args.out)
    if out.exists():raise RuntimeError('Preserve existing run')
    out.with_suffix('.harness.py').write_bytes(Path(__file__).read_bytes())
    model_class=RegionModel
    policy=ROOT/'mapwalker/region_model.py'
    if args.compact_core:
        from adapted_region_probe import RegionModel as model_class
        policy=ROOT/'tools/adapted_region_probe.py'
        out.with_suffix('.policy.py').write_bytes(policy.read_bytes())
    if args.consensus:
        from consensus_region_probe import RegionModel as model_class
        policy=ROOT/'tools/consensus_region_probe.py'
        out.with_suffix('.policy.py').write_bytes(policy.read_bytes())
    torch.cuda.reset_peak_memory_stats();start=time.perf_counter();model=model_class(args.weights);init_ms=(time.perf_counter()-start)*1000
    manifest=Path(args.manifest)
    for s in json.loads(manifest.read_text('utf-8'))['scenes']:
        path=manifest.parent/s['path'];assert hashlib.sha256(path.read_bytes()).hexdigest()==s['sha256']
        tick=time.perf_counter();im=Image.open(path).convert('RGB');decode_ms=(time.perf_counter()-tick)*1000
        tick=time.perf_counter();ps=model(im);elapsed=(time.perf_counter()-tick)*1000
        with out.open('a',encoding='utf-8') as f:f.write(json.dumps(dict(scene=s['id'],proposals=ps,decode_ms=decode_ms,total_inference_ms=elapsed))+'\n')
        print(s['id'],len(ps),round(elapsed),flush=True)
    out.with_suffix('.meta.json').write_text(json.dumps(dict(init_ms=init_ms,peak_allocated_mib=torch.cuda.max_memory_allocated()/1024**2,weights_sha256=hashlib.sha256(Path(args.weights).read_bytes()).hexdigest(),harness_sha256=hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),policy_sha256=hashlib.sha256(policy.read_bytes()).hexdigest(),inputs_sha256=hashlib.sha256(manifest.read_bytes()).hexdigest()),indent=2),'utf-8')
if __name__=='__main__':main()
