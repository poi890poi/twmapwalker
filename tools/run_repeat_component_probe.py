import hashlib,json,sys,time
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from PIL import Image,ImageDraw
from repeat_component_probe import repeat_evidence
from mapwalker.display import priority
from report_detection_round3 import score

out=ROOT/'evidence/detection-round4';data=json.loads((ROOT/'evidence/detection-round3/review-data.json').read_text('utf8'))
result={};metrics={}
for split,suite in data.items():
    before={};after={};records=[]
    for scene in suite['scenes']:
        path=ROOT/'evidence/detection-round3'/scene['path'];assert hashlib.sha256(path.read_bytes()).hexdigest()==scene['sha256']
        image=Image.open(path).convert('RGB');ps=suite['new_all'][scene['id']]
        tick=time.perf_counter();candidate=repeat_evidence(image,ps)
        records.append(dict(scene=scene['id'],proposals=candidate,ms=(time.perf_counter()-tick)*1000))
        before[scene['id']]=[p for p in ps if priority(p)>=.74]
        after[scene['id']]=[p for p in candidate if priority(p)>=.74 and not p['details']['repeat_patch_texture']]
    refs=ROOT/('evidence/symbol-first/references.json' if split=='development' else f'evidence/detection-round3/{"fresh" if split=="fresh" else "final"}-references.json')
    refs=json.loads(refs.read_text('utf8'))
    metrics[split]={'before':score(before,refs),'after':score(after,refs)}
    result[split]=records
target=out/'repeat-component-v1.json'
if target.exists():raise RuntimeError('Preserve prior experiment')
target.write_text(json.dumps(result,ensure_ascii=False),encoding='utf8')
(out/'repeat-component-v1-summary.json').write_text(json.dumps(metrics,ensure_ascii=False,indent=2),encoding='utf8')
(out/'repeat-component-v1-code.py').write_bytes((ROOT/'tools/repeat_component_probe.py').read_bytes())
for split,results in metrics.items():print(split,{k:(v['hits'],v['references'],v['background_proposals']) for k,v in results.items()})
print('Flagged',sum(p['details']['repeat_patch_texture'] for rows in result.values() for r in rows for p in r['proposals']))
