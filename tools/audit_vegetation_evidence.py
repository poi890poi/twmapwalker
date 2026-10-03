"""Validate the full read-only production path on all reused cases, including failures."""
import json,sqlite3,time
from PIL import Image
import component_vegetation_trial as trial
from mapwalker.vegetation import analyze
from mapwalker.vegetation_evidence import VegetationEvidence
ROOT=trial.ROOT;OUT=trial.OUT;old=trial.old

def automatic(db,pid):
    row=db.execute('''SELECT p.kind,p.box,t.source,t.z,t.x,t.y,j.manifest,a.spec FROM pois p
      JOIN jobs j ON j.id=p.job_id JOIN tiles t ON t.id=j.tile_id JOIN algorithms a ON a.fingerprint=j.algorithm WHERE p.id=?''',(pid,)).fetchone()
    item=dict(row)
    for k in ('box','manifest','spec'):item[k]=json.loads(item[k])
    return item

if __name__=='__main__':
    if (OUT/'candidate-v2-lock.json').exists():raise RuntimeError('Preserve frozen candidate')
    db=sqlite3.connect('file:'+str(ROOT/'data/mapwalker.sqlite3').replace('\\','/')+'?mode=ro',uri=True);db.row_factory=sqlite3.Row
    rows=trial.rows();labels=old.read(OUT/'fresh/visual-labels.json')['labels']
    for r in old.read(OUT/'fresh/dataset.json'):r['label']=labels[str(r['id'])];rows.append(r)
    service=VegetationEvidence(ROOT/'data');results=[]
    for r in rows:
        start=time.perf_counter()
        if isinstance(r['id'],int):result=service.inspect(automatic(db,r['id']))
        else:result=analyze(Image.open(r['image']),r['crop_box'],16)
        preview=result.pop('preview',None)
        results.append(dict(id=r['id'],label=r['label'],split=r['split'],elapsed_ms=(time.perf_counter()-start)*1000,**result))
    db.close()
    (OUT/'candidate-v2-reused.json').write_text(json.dumps(results,ensure_ascii=False,indent=2),'utf-8')
    (OUT/'candidate-v2-lock.json').write_text(json.dumps(dict(code={n:old.digest(ROOT/'mapwalker'/n) for n in ['vegetation.py','vegetation_evidence.py','reading_suggestions.py']},reader='Existing frozen PP-OCR number reader; any accepted overlapping multi-digit alternative vetoes the vegetation hint, without asserting its transcript is correct.'),indent=2),'utf-8')
    print(json.dumps(dict(hits=[(r['id'],r['label']) for r in results if r['matches']],numeric_vetoes=[(r['id'],r['label']) for r in results if r['status']=='numeric-context']),indent=2))
