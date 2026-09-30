"""Evaluate the frozen blank policy; inputs and outputs remain reviewable."""
import hashlib,json,sys,time
from pathlib import Path
from PIL import Image,ImageDraw,ImageFont
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from mapwalker.coverage_worker import assess,POLICY,CoverageWorker
from mapwalker.db import Store
from mapwalker.detectors import specs
from mapwalker.sources import TileCache
from mapwalker.paths import default_data
OUT=ROOT/'evidence/blank-coverage'

def main():
    target=OUT/'results.json'
    if target.exists():raise RuntimeError('Preserve prior experiment')
    rows=[]
    for source in ('JM50K_1924_new','JM50K_1916'):
        im=Image.open(ROOT/f'evidence/batongguan-review/{source}-original.png')
        for y in range(0,1024,256):
            for x in range(0,1024,256):
                tile=im.crop((x,y,x+256,y+256));start=time.perf_counter();r=assess(tile)
                rows.append(dict(split='development',id=f'{source}-{x}-{y}',source=source,**r,ms=(time.perf_counter()-start)*1000))
    for split,suite in json.loads((ROOT/'evidence/detection-round3/review-data.json').read_text('utf8')).items():
        for scene in suite['scenes']:
            path=ROOT/'evidence/detection-round3'/scene['path'];assert hashlib.sha256(path.read_bytes()).hexdigest()==scene['sha256']
            rows.append(dict(split='prior-mark-'+split,id=scene['id'],**assess(Image.open(path))))
    inputs=json.loads((OUT/'holdout/inputs.json').read_text('utf8'))
    font=ImageFont.truetype('C:/Windows/Fonts/arial.ttf',17)
    sheet=Image.new('RGB',(1056,620),'#f5f3e9');draw=ImageDraw.Draw(sheet)
    for i,s in enumerate(inputs):
        path=OUT/'holdout'/s['path'];assert hashlib.sha256(path.read_bytes()).hexdigest()==s['sha256']
        im=Image.open(path);r=assess(im);rows.append(dict(split='holdout',id=s['path'],source=s['source'],**r))
        x=8+(i%4)*264;y=8+(i//4)*310;label='SKIP: blank paper' if r['blank'] else 'KEEP: content / uncertain'
        draw.text((x,y),label,font=font,fill='#6b6148' if r['blank'] else '#006b4e');sheet.paste(im,(x,y+26))
        draw.text((x,y+284),f"{s['source']} · {s['x']}/{s['y']}",font=font,fill='#223b34')
    sheet.save(OUT/'holdout-comparison.png')
    # Real tile cache + full job lifecycle; isolated store, no production POI changes.
    chosen=next(s for s in inputs if s['source']=='JM50K_1924_new' and assess(Image.open(OUT/'holdout'/s['path']))['blank'])
    run_root=ROOT/'data/blank-coverage-check';run_root.mkdir(exist_ok=True)
    db=run_root/'jobs.sqlite3'
    if db.exists():raise RuntimeError('Preserve previous isolated job run')
    store=Store(db);registry=specs();store.register(registry);store.enqueue(chosen['source'],[(chosen['z'],chosen['x'],chosen['y'])])
    worker=CoverageWorker(store,TileCache(default_data()));start=time.perf_counter()
    for _ in registry:assert worker.once()
    assert not worker.once()
    elapsed=time.perf_counter()-start
    with store.connect() as conn:jobs=[dict(r) for r in conn.execute('SELECT state,telemetry,manifest FROM jobs ORDER BY id')]
    for j in jobs:
        j['telemetry']=json.loads(j['telemetry']);j['manifest']=json.loads(j['manifest'])
        assert j['state']=='complete' and j['telemetry']['skipped_reason']=='blank_historical_map'
    assert worker.ocr is None and worker.regions is None
    result=dict(policy=POLICY,rows=rows,isolated_job_run=dict(seconds=elapsed,jobs=jobs,model_loaded=False))
    target.write_text(json.dumps(result,indent=2),encoding='utf8')
    for split in sorted({r['split'] for r in rows}):
        subset=[r for r in rows if r['split']==split];print(split,'skipped',sum(r['blank'] for r in subset),'of',len(subset))
    print('Six cached tile checks:',round(elapsed,3),'seconds; no models loaded')

if __name__=='__main__':main()
