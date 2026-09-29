import hashlib,json,sys,time
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from PIL import Image,ImageDraw,ImageFont
from mapwalker.trails import trail_proposals
from connected_trail_probe import connected_trails
out=ROOT/'evidence/trail-round4';suite=json.loads((out/'inputs.json').read_text())
target=out/'connected-v1.json'
if target.exists():raise RuntimeError('Preserve prior output')
results=[]
for scene in suite['scenes']:
    path=out/scene['path'];assert hashlib.sha256(path.read_bytes()).hexdigest()==scene['sha256']
    im=Image.open(path).convert('RGB');runs=[]
    for method in ('baseline','connected-135','connected-110'):
        start=time.perf_counter()
        if method=='baseline':
            ps=trail_proposals(im,{'ink_threshold':135})
            paths=[dict(points=p['details']['pixel_path'],dashes=p['details']['dash_count']) for p in ps];meta={}
        else:paths,meta=connected_trails(im,int(method.split('-')[1]))
        ms=(time.perf_counter()-start)*1000
        panel=im.copy();draw=ImageDraw.Draw(panel)
        for p in paths:draw.line([tuple(v) for v in p['points']],fill='#e22d5a',width=3)
        panel.save(out/(scene['id']+'-'+method+'.png'))
        runs.append(dict(method=method,paths=paths,ms=ms,**meta));print(scene['id'],method,len(paths),round(ms),flush=True)
    results.append(dict(scene=scene['id'],runs=runs))
target.write_text(json.dumps(results,indent=2));(out/'connected-v1-code.py').write_bytes((ROOT/'tools/connected_trail_probe.py').read_bytes())
