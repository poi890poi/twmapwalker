"""Post-lock, ring-enriched spatial check; references never enter inference."""
import argparse,hashlib,json,sqlite3,time
import numpy as np
from PIL import Image,ImageDraw
import native_pattern_trial as trial
import native_symbol_trial as symbol
old=trial.old;ROOT=trial.ROOT;OUT=trial.OUT/'fresh'


def write(name,value):
    (OUT/name).write_text(json.dumps(value,ensure_ascii=False,indent=2),'utf-8')


def freeze():
    assert (trial.OUT/'symbol-lock.json').exists()
    if (OUT/'dataset.json').exists():raise RuntimeError('Frozen holdout exists')
    OUT.mkdir(exist_ok=True);(OUT/'crops').mkdir(exist_ok=True)
    prior=[r for r in old.read(trial.OUT/'dataset.json') if 'source' in r]
    prior+=old.read(ROOT/'evidence/symbol-first/inputs.json')['scenes']
    db=sqlite3.connect('file:'+str(ROOT/'data/mapwalker.sqlite3').replace('\\','/')+'?mode=ro',uri=True);db.row_factory=sqlite3.Row
    pool=[]
    for row in db.execute('''SELECT p.id,p.box,p.kind,p.score,t.source,t.z,t.x,t.y FROM pois p
        JOIN jobs j ON j.id=p.job_id JOIN tiles t ON t.id=j.tile_id JOIN algorithms a ON a.fingerprint=j.algorithm
        WHERE a.active=1 AND j.state='complete' AND p.kind IN ('text','symbol')'''):
        r=dict(row);r['box']=json.loads(r['box']);b=r['box']
        if not (2<=min(b[2]-b[0],b[3]-b[1]) and max(b[2]-b[0],b[3]-b[1])<=160):continue
        if any(old.near(r,a,2) for a in prior):continue
        r['block']=f"{r['source']}:{r['z']}:{r['x']//4}:{r['y']//4}"
        r['order']=hashlib.sha256(f"native-patterns-31003:{r['id']}".encode()).hexdigest();pool.append(r)
    db.close();rows=[];used=set();counts={};missing=[]
    for r in sorted(pool,key=lambda r:r['order']):
        if r['block'] in used:continue
        if counts.get((r['source'],'ring'),0)>=16 and counts.get((r['source'],'other'),0)>=8:continue
        try:im,box,provenance=old.crop_cached(r)
        except FileNotFoundError:missing.append(r['id']);continue
        gray=np.asarray(im.convert('L'));cx=(box[0]+box[2])/2;cy=(box[1]+box[3])/2
        hh=[h for h in symbol.holes(gray) if box[0]<=h['center'][0]<=box[2] and box[1]<=h['center'][1]<=box[3] and np.linalg.norm(np.array(h['center'])-[cx,cy])<=12]
        stratum='ring' if hh else 'other';key=(r['source'],stratum)
        if counts.get(key,0)>=(16 if hh else 8):continue
        path=OUT/'crops'/f"{r['id']}.png";im.save(path);r.pop('order')
        r.update(image=str(path),crop=f"crops/{r['id']}.png",crop_box=box,sha256=old.digest(path),sources=provenance,stratum=stratum,split='fresh-spatial',label='unreviewed',physical_group=str(r['id']))
        rows.append(r);used.add(r['block']);counts[key]=counts.get(key,0)+1
    write('dataset.json',rows);write('selection.json',dict(counts={':'.join(k):v for k,v in counts.items()},eligible=len(pool),missing_context=missing,rule='Hash order, up to 16 ring-eligible and 8 other candidates per edition, one per 4x4 block, two-tile buffers from every earlier sample area. Ring enrichment is conditional sampling, not prevalence.',locks={n:old.digest(trial.OUT/n) for n in ['locked-model.json','symbol-lock.json']}))
    for start in range(0,len(rows),24):
        batch=rows[start:start+24];canvas=Image.new('RGB',(1000,math.ceil(len(batch)/5)*225),'white');d=ImageDraw.Draw(canvas)
        for i,r in enumerate(batch):
            x=i%5*200;y=i//5*225;im=Image.open(r['image']).convert('RGB');ImageDraw.Draw(im).rectangle(r['crop_box'],outline='red',width=1)
            im.thumbnail((190,185));canvas.paste(im.resize((190,185)),(x,y+30));d.text((x,y+3),str(r['id'])+' '+r['stratum'],fill='black')
        canvas.save(OUT/f'sheet-{start//24}.jpg')
    print(json.dumps({':'.join(k):v for k,v in counts.items()}))


def infer():
    rr=old.read(OUT/'dataset.json');xx=np.load(trial.OUT/'features.npz');lock=old.read(trial.OUT/'locked-model.json')['methods']['native-broad']
    ids=np.array(lock['fit_indices']);model=old.train(xx['native'][ids],np.array(lock['fit_labels']))
    sx=np.load(trial.OUT/'symbol-features.npz')['features'];sl=old.read(trial.OUT/'symbol-lock.json');si=np.array(sl['fit_indices']);sm=old.train(sx[si],np.array(sl['fit_labels']));out=[]
    for r in rr:
        start=time.perf_counter();vv,valid=trial.views(r);v=trial.HOG.compute(np.asarray(vv['native'])).ravel();v=v/max(1e-8,np.linalg.norm(v));score,ratio=old.predict(model,v[None]);native=bool(valid and score[0]>lock['threshold'] and ratio[0]<.8)
        sv,h=symbol.extract(r)
        if sv is None:ss,sq,yes=None,None,False
        else:
            a,b=old.predict(sm,sv[None]);ss=float(a[0]);sq=float(b[0]);yes=ss>sl['threshold'] and sq<.8
        out.append(dict(id=r['id'],native=dict(reject=native,score=float(score[0]),ratio=float(ratio[0]),in_scope=valid),symbol=dict(reject=yes,score=ss,ratio=sq,hole=h),ms=(time.perf_counter()-start)*1000))
    write('predictions.json',out);print('Predictions saved; score only after independent visual labeling.')


if __name__=='__main__':
    import math
    p=argparse.ArgumentParser();p.add_argument('stage',choices=['freeze','infer']);globals()[p.parse_args().stage]()
