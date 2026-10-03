"""Gather unseen geographic contexts and freeze topology predictions before review."""
import json
import math
import sqlite3
from collections import Counter

from PIL import ImageDraw, Image

from mapwalker.reading_suggestions import evidence_crop
from .contour_frequency_trial import ROOT,sha
from .mine_contour_samples import PRIOR,digest
from .contour_topology_trial import features,PARAMETERS

OUT=ROOT/'evidence/contour-topology/fresh'


def main():
    OUT.mkdir(exist_ok=False);(OUT/'crops').mkdir()
    old=[]
    paths=[ROOT/'evidence'/name for name in PRIOR]+[ROOT/'evidence/contour-samples/dataset.json']
    for path in paths:
        data=json.loads(path.read_text(encoding='utf8'))
        old.extend(data.get('scenes',[]) if isinstance(data,dict) else data)
    excluded={(r['x']+dx,r['y']+dy) for r in old if r.get('z')==16 and 'x' in r
              for dx in range(-2,3) for dy in range(-2,3)}
    db=sqlite3.connect('file:'+str(ROOT/'data/mapwalker.sqlite3').replace('\\','/')+'?mode=ro',uri=True)
    db.row_factory=sqlite3.Row
    pool=[]
    for row in db.execute('''SELECT p.id,p.kind,p.text,p.score,p.box,p.details,t.source,t.z,t.x,t.y,a.spec,j.manifest
        FROM pois p JOIN jobs j ON j.id=p.job_id JOIN tiles t ON t.id=j.tile_id
        JOIN algorithms a ON a.fingerprint=j.algorithm
        WHERE a.active=1 AND j.state='complete' AND p.disposition='candidate' AND t.z=16 AND p.kind IN ('symbol','text')'''):
        r=dict(row)
        if (r['x'],r['y']) in excluded:continue
        for key in ('box','details','spec','manifest'):r[key]=json.loads(r[key])
        w,h=r['box'][2]-r['box'][0],r['box'][3]-r['box'][1]
        if min(w,h)<3 or max(w,h)>96 or max(w,h)<20:continue
        r['order']=digest(f'contour-topology-fresh-20261003:{r["id"]}'.encode())
        pool.append(r)
    db.close()
    rows=[];used=set();counts=Counter();errors=[]
    for r in sorted(pool,key=lambda r:r['order']):
        key=(r['source'],r['kind']);block=(r['x']//4,r['y']//4)
        # One per new geographic block, shared across editions; buffer every new sample.
        if counts[key]>=6 or block in used:continue
        if any(max(abs(r['x']-v['x']),abs(r['y']-v['y']))<3 for v in rows):continue
        a,b,c,d=r['box'];left=math.floor((a+c)/2)-96;top=math.floor((b+d)/2)-96
        item={**r,'box':[left,top,left+192,top+192]}
        try:im,_,provenance=evidence_crop(ROOT/'data',item,0)
        except (OSError,ValueError) as exc:
            errors.append(dict(id=r['id'],error=str(exc)));continue
        crop=f'crops/{r["id"]}.png';im.save(OUT/crop)
        box=[a-left,b-top,c-left,d-top]
        f=features(im,box)
        rows.append({k:r[k] for k in ('id','source','z','x','y','kind','box')} |
                    dict(index=len(rows)+1,crop=crop,sha256=sha(OUT/crop),context_box=box,sources=provenance,
                         features=f,rejected=f.get('topology_and_parallel',False)))
        used.add(block);counts[key]+=1
    (OUT/'predictions.json').write_text(json.dumps(rows,indent=2)+'\n',encoding='utf8')
    (OUT/'lock.json').write_text(json.dumps(dict(parameters=PARAMETERS,
        code_sha256=sha(ROOT/'tools/contour_topology_trial.py'),predictions_sha256=sha(OUT/'predictions.json'),
        prior_hashes={str(p.relative_to(ROOT)):sha(p) for p in paths},pool=len(pool),count=len(rows),
        selection='Fixed hash ordering, up to 6 per edition/kind, at least 3 tile-index distance from named prior studies and other selected samples. Predictions saved before viewing.',
        missing_context=errors),indent=2)+'\n',encoding='utf8')
    for start in range(0,len(rows),12):
        batch=rows[start:start+12]
        board=Image.new('RGB',(1200,320*math.ceil(len(batch)/4)),'white');draw=ImageDraw.Draw(board)
        for i,r in enumerate(batch):
            x=i%4*300;y=i//4*320
            with Image.open(OUT/r['crop']) as im:im=im.copy()
            ImageDraw.Draw(im).rectangle(r['context_box'],outline='red',width=1)
            board.paste(im.resize((288,288),Image.Resampling.NEAREST),(x+6,y+29))
            draw.text((x+6,y+3),f"{r['index']} POI {r['id']} {r['source']}",fill='black')
        board.save(OUT/f'sheet-{start//12}.jpg',quality=94)
    print(f'Frozen {len(rows)} new contexts and predictions from {len(pool)} eligible proposals; no prediction values displayed.')


if __name__=='__main__':main()
