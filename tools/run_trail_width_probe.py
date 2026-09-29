import hashlib,json,sys,time
from pathlib import Path
from PIL import Image,ImageDraw
from connected_trail_probe import connected_trails
ROOT=Path(__file__).resolve().parents[1];out=ROOT/'evidence/trail-round4'
target=out/'width-v1.json'
if target.exists():raise RuntimeError('Preserve prior run')
rows=[]
for scene in json.loads((out/'inputs.json').read_text())['scenes']:
    path=out/scene['path'];assert hashlib.sha256(path.read_bytes()).hexdigest()==scene['sha256']
    im=Image.open(path).convert('RGB');start=time.perf_counter()
    paths,meta=connected_trails(im,135,3.5)
    seconds=time.perf_counter()-start
    draw=ImageDraw.Draw(im)
    for p in paths:draw.line([tuple(v) for v in p['points']],fill='#e22d5a',width=3)
    im.save(out/(scene['id']+'-width.png'))
    rows.append(dict(scene=scene['id'],seconds=seconds,paths=paths,**meta));print(scene['id'],len(paths),meta)
target.write_text(json.dumps(rows,indent=2))
