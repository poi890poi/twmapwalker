"""Post-lock precision audit plus text/unselected controls on new map areas."""
import hashlib,json,math,re,sqlite3,time
import numpy as np
from PIL import Image,ImageDraw
import component_vegetation_trial as trial
from mapwalker.vegetation import analyze
old=trial.old;ROOT=trial.ROOT;OUT=trial.OUT/'fresh'

def main():
    lock=old.read(trial.OUT/'candidate-lock.json')
    assert old.digest(ROOT/'mapwalker/vegetation.py')==lock['code_sha256']
    if (OUT/'dataset.json').exists():raise RuntimeError('Frozen holdout exists')
    OUT.mkdir(exist_ok=True);(OUT/'crops').mkdir(exist_ok=True)
    oldrows=[r for r in trial.rows() if 'source' in r]+old.read(ROOT/'evidence/symbol-first/inputs.json')['scenes']
    db=sqlite3.connect('file:'+str(ROOT/'data/mapwalker.sqlite3').replace('\\','/')+'?mode=ro',uri=True);db.row_factory=sqlite3.Row;pool=[]
    for row in db.execute('''SELECT p.id,p.box,p.kind,p.score,p.text,t.source,t.z,t.x,t.y FROM pois p
      JOIN jobs j ON j.id=p.job_id JOIN tiles t ON t.id=j.tile_id JOIN algorithms a ON a.fingerprint=j.algorithm
      WHERE a.active=1 AND j.state='complete' AND p.kind IN ('text','symbol')'''):
        r=dict(row);r['box']=json.loads(r['box']);b=r['box']
        if r['z']!=16 or not (2<=min(b[2]-b[0],b[3]-b[1]) and max(b[2]-b[0],b[3]-b[1])<=240):continue
        if any(old.near(r,a,2) for a in oldrows):continue
        r['block']=f"{r['source']}:{r['z']}:{r['x']//4}:{r['y']//4}";r['order']=hashlib.sha256(f"component-audit-31003:{r['id']}".encode()).hexdigest();pool.append(r)
    db.close();selected=[];used=set();counts={};scanned=0;missing=[];start=time.perf_counter()
    quotas={'flagged':12,'text-control':8,'unselected':8}
    for r in sorted(pool,key=lambda r:r['order']):
        if r['block'] in used:continue
        if all(counts.get((r['source'],s),0)>=q for s,q in quotas.items()):continue
        try:im,box,provenance=old.crop_cached(r)
        except FileNotFoundError:missing.append(r['id']);continue
        tick=time.perf_counter();result=analyze(im,box,16);ms=(time.perf_counter()-tick)*1000;scanned+=1
        text=r.pop('text');stratum='flagged' if result['matches'] else 'text-control' if re.search(r'[\u3040-\u30ff\u3400-\u9fff]',text) else 'unselected';key=(r['source'],stratum)
        if counts.get(key,0)>=quotas[stratum]:continue
        path=OUT/'crops'/f"{r['id']}.png";im.save(path);r.pop('order');r.update(image=str(path),crop=f"crops/{r['id']}.png",crop_box=box,sha256=old.digest(path),sources=provenance,stratum=stratum,split='fresh-spatial',label='unreviewed',physical_group=str(r['id']),prediction=result,ms=ms)
        selected.append(r);used.add(r['block']);counts[key]=counts.get(key,0)+1
        if len(selected)%8==0:print('selected',len(selected),'scanned',scanned,flush=True)
    def write(name,obj):(OUT/name).write_text(json.dumps(obj,ensure_ascii=False,indent=2),'utf-8')
    write('dataset.json',selected);write('selection.json',dict(counts={':'.join(k):v for k,v in counts.items()},eligible=len(pool),scanned=scanned,missing=missing,elapsed_s=time.perf_counter()-start,lock_sha256=old.digest(trial.OUT/'candidate-lock.json'),rule='Deterministic hash order; one candidate per 4x4 block; exclude every earlier 2-tile neighborhood. Per edition: up to12 predicted positives,8 raw CJK/Kana-read controls,8 other unselected. Conditional precision audit, not prevalence or recall.'))
    # Hide prediction/stratum in the review sheets. References are written separately.
    for start in range(0,len(selected),24):
        batch=selected[start:start+24];sheet=Image.new('RGB',(1000,math.ceil(len(batch)/5)*220),'white');d=ImageDraw.Draw(sheet)
        for j,r in enumerate(batch):
            x=j%5*200;y=j//5*220;im=Image.open(r['image']).convert('RGB');ImageDraw.Draw(im).rectangle(r['crop_box'],outline='red',width=1);im.thumbnail((190,180));sheet.paste(im.resize((190,180)),(x,y+30));d.text((x+3,y+5),str(r['id']),fill='black')
        sheet.save(OUT/f'sheet-{start//24}.jpg')
    print(json.dumps({':'.join(k):v for k,v in counts.items()}),flush=True)

if __name__=='__main__':main()
