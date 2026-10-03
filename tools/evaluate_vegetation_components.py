"""Freeze deployment candidate and score reused diagnostics before fresh checks."""
import json,time
from PIL import Image
import component_vegetation_trial as trial
from mapwalker.vegetation import analyze

if __name__=='__main__':
    results=[];rows=trial.rows()
    for r in rows:
        im=Image.open(r['image']).convert('RGB');start=time.perf_counter();v=analyze(im,r['crop_box'],r.get('z',16))
        results.append(dict(id=r['id'],label=r['label'],split=r['split'],ms=(time.perf_counter()-start)*1000,**v))
    path=trial.OUT/'candidate-development.json'
    if path.exists():raise RuntimeError('Do not overwrite frozen development output')
    path.write_text(json.dumps(results,ensure_ascii=False,indent=2),'utf-8')
    (trial.OUT/'candidate-lock.json').write_text(json.dumps(dict(version='native-component-1',code_sha256=trial.old.digest(trial.ROOT/'mapwalker/vegetation.py'),inputs=[dict(id=r['id'],path=r['image'],sha256=r['sha256']) for r in rows],policy='Advisory only; no automatic classification or hiding'),indent=2),'utf-8')
    print(json.dumps({label:dict(total=sum(r['label']==label for r in results),hits=[r['id'] for r in results if r['label']==label and r['matches']]) for label in sorted({r['label'] for r in results})},indent=2))
