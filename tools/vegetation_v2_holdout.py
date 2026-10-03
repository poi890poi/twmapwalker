"""Post-lock new-pixel precision check of the full advisory service."""
import hashlib,json,math,re,sqlite3,time
from PIL import Image,ImageDraw
import component_vegetation_trial as trial
from audit_vegetation_evidence import automatic
from mapwalker.reading_suggestions import evidence_crop
from mapwalker.vegetation import analyze
from mapwalker.vegetation_evidence import VegetationEvidence
ROOT=trial.ROOT;old=trial.old;OUT=trial.OUT/'fresh-v2'

def main():
    lock=old.read(trial.OUT/'candidate-v2-lock.json')
    for name,digest in lock['code'].items():assert old.digest(ROOT/'mapwalker'/name)==digest
    if (OUT/'dataset.json').exists():raise RuntimeError('Preserve frozen check')
    (OUT/'crops').mkdir(parents=True,exist_ok=True)
    previous=[r for r in trial.rows()+old.read(trial.OUT/'fresh/dataset.json')+old.read(ROOT/'evidence/symbol-first/inputs.json')['scenes'] if 'source' in r]
    def bounds(r):
        b=r.get('box',[-256,-256,512,512]);return [r['x']*256+b[0]-64,r['y']*256+b[1]-64,r['x']*256+b[2]+64,r['y']*256+b[3]+64]
    prior=[(r['source'],r['z'],bounds(r)) for r in previous]
    def overlaps_prior(r):
        b=bounds(r)
        return any(s==r['source'] and z==r['z'] and
                   ((b[0]<a[2] and a[0]<b[2] and b[1]<a[3] and a[1]<b[3]) or
                    math.dist(((b[0]+b[2])/2,(b[1]+b[3])/2),((a[0]+a[2])/2,(a[1]+a[3])/2))<192)
                   for s,z,a in prior)
    db=sqlite3.connect('file:'+str(ROOT/'data/mapwalker.sqlite3').replace('\\','/')+'?mode=ro',uri=True);db.row_factory=sqlite3.Row
    pool=[]
    for row in db.execute('''SELECT p.id,p.box,p.kind,p.text,t.source,t.z,t.x,t.y FROM pois p
      JOIN jobs j ON j.id=p.job_id JOIN tiles t ON t.id=j.tile_id JOIN algorithms a ON a.fingerprint=j.algorithm
      WHERE a.active=1 AND j.state='complete' AND p.kind IN ('text','symbol')'''):
        r=dict(row);r['box']=json.loads(r['box']);b=r['box']
        if r['z']!=16 or not(2<=min(b[2]-b[0],b[3]-b[1]) and max(b[2]-b[0],b[3]-b[1])<=240) or overlaps_prior(r):continue
        r['order']=hashlib.sha256(f"vegetation-v2-31003:{r['id']}".encode()).hexdigest();pool.append(r)
    selected=[];used=set();counts={};scanned=0;missing=[];start=time.perf_counter();service=VegetationEvidence(ROOT/'data')
    quotas={'geometry-positive':8,'text-control':6,'unselected':4}
    for r in sorted(pool,key=lambda r:r['order']):
        block=(r['source'],r['x']//4,r['y']//4)
        if block in used or all(counts.get((r['source'],s),0)>=n for s,n in quotas.items()):continue
        item=automatic(db,r['id'])
        try:im,box,pixels=evidence_crop(ROOT/'data',item,24)
        except (FileNotFoundError,ValueError) as exc:missing.append(dict(id=r['id'],error=str(exc)));continue
        geometry=analyze(im,box,16);scanned+=1
        stratum='geometry-positive' if geometry['matches'] else 'text-control' if re.search(r'[\u3040-\u30ff\u3400-\u9fff]',r['text']) else 'unselected'
        key=(r['source'],stratum)
        if counts.get(key,0)>=quotas[stratum]:continue
        tick=time.perf_counter();result=service.inspect(item);result.pop('preview',None)
        path=OUT/'crops'/f"{r['id']}.png";im.save(path)
        r.pop('text');r.pop('order');r.update(image=str(path),crop=f"crops/{r['id']}.png",crop_box=box,sha256=old.digest(path),pixels=pixels,stratum=stratum,prediction=result,ms=(time.perf_counter()-tick)*1000)
        selected.append(r);used.add(block);counts[key]=counts.get(key,0)+1
        print('selected',len(selected),'scanned',scanned,flush=True)
    db.close()
    for name,obj in [('dataset.json',selected),('selection.json',dict(counts={':'.join(k):v for k,v in counts.items()},scanned=scanned,eligible=len(pool),missing=missing,elapsed_s=time.perf_counter()-start,lock_sha256=old.digest(trial.OUT/'candidate-v2-lock.json'),sampler_sha256=old.digest(__file__),rule='New pixels, all earlier crops excluded including 64px reader context, minimum 192px center distance; one example per4x4 block. Conditional precision audit; not geographically independent or prevalence/recall.'))]:
        (OUT/name).write_text(json.dumps(obj,ensure_ascii=False,indent=2),'utf-8')
    for start in range(0,len(selected),18):
        batch=selected[start:start+18];sheet=Image.new('RGB',(1200,math.ceil(len(batch)/6)*250),'white');d=ImageDraw.Draw(sheet)
        for j,r in enumerate(batch):
            x=j%6*200;y=j//6*250;im=Image.open(r['image']).convert('RGB');ImageDraw.Draw(im).rectangle(r['crop_box'],outline='red',width=1);im.thumbnail((194,210));scale=min(194/im.width,210/im.height);im=im.resize((round(im.width*scale),round(im.height*scale)),Image.Resampling.NEAREST);sheet.paste(im,(x,y+30));d.text((x+3,y+5),str(r['id']),fill='black')
        sheet.save(OUT/f'sheet-{start//18}.jpg')
    print(json.dumps({':'.join(k):v for k,v in counts.items()}),flush=True)

if __name__=='__main__':main()
