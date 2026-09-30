"""Frozen real-image trial; OSM is used only after image-only inference."""
import argparse,hashlib,json,sys,time
from pathlib import Path
import cv2,numpy as np,torch
from PIL import Image,ImageDraw
from synthetic_dash_model import DashNet,infer,connect
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from mapwalker.trails import trail_proposals
OUT=ROOT/'evidence/trail-round5';SOURCE=ROOT/'evidence/trail-area-comparison'

def render(im,mask,paths,target):
    arr=np.asarray(im).copy().astype(float);on=mask>0
    arr[on]=arr[on]*.25+np.array([239,30,87])*.75
    result=Image.fromarray(arr.astype(np.uint8));draw=ImageDraw.Draw(result)
    for p in paths:draw.line([tuple(v) for v in p['points']],fill='#008abe',width=2)
    result.save(target)

def run_scene(model,scene):
    name=scene['id'];path=Path(scene['path']);target=OUT/f'{name}.json'
    if target.exists():raise RuntimeError('Preserve existing results: '+name)
    im=Image.open(path).convert('RGB');gray=np.asarray(im.convert('L'))
    torch.cuda.reset_peak_memory_stats();torch.cuda.synchronize();start=time.perf_counter()
    prob=infer(model,gray);torch.cuda.synchronize();inference=time.perf_counter()-start
    np.save(OUT/f'{name}-likelihood.npy',prob)
    Image.fromarray((prob*255).astype(np.uint8)).save(OUT/f'{name}-likelihood.png')
    im.save(OUT/f'{name}-original.png')
    start=time.perf_counter();baseline=trail_proposals(im,{'ink_threshold':135});baseline_s=time.perf_counter()-start
    bp=[dict(points=p['details']['pixel_path']) for p in baseline]
    render(im,np.zeros(gray.shape,np.uint8),bp,OUT/f'{name}-baseline.png')
    start=time.perf_counter();keep,paths=connect(prob);connection_s=time.perf_counter()-start
    render(im,prob>=.5,[],OUT/f'{name}-dense.png');render(im,keep,paths,OUT/f'{name}-connected.png')
    # Prior only removes support: it never adds likelihood or moves pixels.
    corridor=np.zeros(gray.shape,np.uint8);shifted=np.zeros_like(corridor)
    for s in scene['segments']:
        points=np.rint(s['points']).astype(np.int32)
        cv2.polylines(corridor,[points],False,1,320)
        cv2.polylines(shifted,[points+np.array([0,-320])],False,1,320)
    rows=[]
    for label,region in [('guided',corridor),('shift-control',shifted)]:
        start=time.perf_counter();k,ps=connect(prob*region);seconds=time.perf_counter()-start
        render(im,k,ps,OUT/f'{name}-{label}.png')
        rows.append(dict(method=label,paths=ps,connected_ink_pixels=int(k.sum()),region_pixels=int(region.sum()),connection_s=seconds))
    guide=im.copy();draw=ImageDraw.Draw(guide)
    for s in scene['segments']:draw.line([tuple(v) for v in s['points']],fill='#c68c00',width=3)
    guide.save(OUT/f'{name}-osm.png')
    result=dict(id=name,label=scene['label'],source=scene['source'],input_sha256=hashlib.sha256(path.read_bytes()).hexdigest(),
        inference_s=inference,baseline_s=baseline_s,connection_s=connection_s,baseline_paths=bp,dense_pixels=int((prob>=.5).sum()),connected_ink_pixels=int(keep.sum()),paths=paths,variants=rows,
        peak_allocated_mb=torch.cuda.max_memory_allocated()/2**20,baseline_code_sha256=hashlib.sha256((ROOT/'mapwalker/trails.py').read_bytes()).hexdigest())
    target.write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding='utf8')
    print(name,'dense',result['dense_pixels'],'paths',len(paths),'guided',len(rows[0]['paths']),'seconds',round(inference,2),flush=True)
    return result

def main():
    global OUT
    parser=argparse.ArgumentParser();parser.add_argument('--areas',default='N,J');parser.add_argument('--holdout',action='store_true');parser.add_argument('--worn',action='store_true');args=parser.parse_args()
    if args.worn:OUT=OUT/'worn'
    training=json.loads((OUT/'training.json').read_text());weights=ROOT/'data/trail-round5/dashnet.pt'
    if args.worn:
        weights=weights.parent/'worn/dashnet.pt'
        assert hashlib.sha256((ROOT/'tools/synthetic_dash_worn.py').read_bytes()).hexdigest()==training['augmentation_sha256']
    assert hashlib.sha256(weights.read_bytes()).hexdigest()==training['weights_sha256']
    assert hashlib.sha256((ROOT/'tools/synthetic_dash_model.py').read_bytes()).hexdigest()==training['code_sha256']
    torch.set_num_threads(2);model=DashNet().cuda().eval();model.load_state_dict(torch.load(weights,map_location='cuda',weights_only=True))
    scenes=[]
    if args.holdout:scenes=json.loads((ROOT/'evidence/trail-round5/holdout-inputs.json').read_text('utf8'))
    else:
        for a in json.loads((SOURCE/'areas.json').read_text('utf8')):
            if a['id'] not in args.areas.split(','):continue
            for source in ('JM50K_1916','JM50K_1924_new'):
                scenes.append(dict(id=f'{a["id"]}-{source}',label=a['name'],source=source,path=str(SOURCE/f'{a["id"]}-{source}-original.png'),segments=a['segments']))
    for s in scenes:run_scene(model,s)

if __name__=='__main__':main()
