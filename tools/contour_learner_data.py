"""Freeze a contour-classifier experiment; read-only database and native pixels."""
import hashlib
import json
import math
import sqlite3
from collections import Counter
from pathlib import Path

from PIL import Image, ImageDraw, ImageOps
from mapwalker.reading_suggestions import evidence_crop

ROOT=Path(__file__).resolve().parents[1]
OUT=ROOT/'evidence/contour-learner'
SEED='contour-learner-20261003-v1'


def sha(path):return hashlib.sha256(path.read_bytes()).hexdigest()
def read(path):return json.loads(path.read_text(encoding='utf8'))
def write(path,data):path.write_text(json.dumps(data,ensure_ascii=False,indent=2)+'\n',encoding='utf8')
def order(value):return hashlib.sha256(f'{SEED}:{value}'.encode()).hexdigest()
def block(r):return f"{r['x']//4}:{r['y']//4}"
def reserved(r):return int(order('split:'+block(r))[:8],16)%5==0
def near(a,b):return a.get('z')==b.get('z') and 'x' in a and 'x' in b and max(abs(a['x']-b['x']),abs(a['y']-b['y']))<=2


def sheets(rows,folder,prefix):
    for start in range(0,len(rows),12):
        batch=rows[start:start+12]
        board=Image.new('RGB',(1200,320*math.ceil(len(batch)/4)),'white');draw=ImageDraw.Draw(board)
        for i,r in enumerate(batch):
            x=i%4*300;y=i//4*320
            with Image.open(ROOT/r['context']) as im:im=im.convert('RGB')
            ImageDraw.Draw(im).rectangle(r['context_box'],outline='red',width=1)
            board.paste(ImageOps.contain(im,(288,288),Image.Resampling.NEAREST),(x+6,y+29))
            draw.text((x+6,y+3),f"{r['index']}  POI {r['id']}  {r['source']}",fill='black')
        board.save(folder/f'{prefix}-{start//12}.jpg',quality=94)


def main():
    OUT.mkdir(exist_ok=False);(OUT/'crops').mkdir()
    write(OUT/'contract.json',dict(type='Offline learned classifier experiment; no production writes unless later evidence supports them',
        causal_inputs='Native pixels, target box; appearance versus same appearance plus size, frequency and topology. No OCR strings, annotation labels, source edition or geographic coordinates in inference.',
        labels='Assistant visual review of boxed targets, separately joined after automatic feature extraction; unknown marks protected.',
        model='Fixed 160-tree OpenCV random forest, depth 8, minimum sample count 3; paired feature ablation',
        calibration='Five spatial folds with same-block and two-tile exclusion; threshold strictly above largest out-of-fold protected score by 0.025. No held-out tuning.',
        acceptance='At least 25% development contour removal at calibrated threshold; zero flags on reused protection probes. Surviving candidate must remove at least 25% held-out contours with zero protected/uncertain flags. Automatic hiding additionally requires positive coverage of names, numbers, Kana and rare symbols in separate evaluation; insufficient coverage stays offline.',
        limitations='New target collection can revisit geographic areas seen in prior research. Train/test are spatially separated for this model; not a wholly new map edition or independent human labelling study. Scores are tree vote fractions, not calibrated probabilities.'))
    con=sqlite3.connect('file:'+str(ROOT/'data/mapwalker.sqlite3').replace('\\','/')+'?mode=ro',uri=True);con.row_factory=sqlite3.Row
    pool=[]
    for row in con.execute('''SELECT p.id,p.kind,p.text,p.score,p.box,p.details,t.source,t.z,t.x,t.y,a.spec,j.manifest
      FROM pois p JOIN jobs j ON j.id=p.job_id JOIN tiles t ON t.id=j.tile_id JOIN algorithms a ON a.fingerprint=j.algorithm
      WHERE a.active=1 AND j.state='complete' AND p.disposition='candidate' AND t.z=16 AND p.kind IN ('text','symbol')'''):
        r=dict(row)
        for k in ('box','details','spec','manifest'):r[k]=json.loads(r[k])
        w,h=r['box'][2]-r['box'][0],r['box'][3]-r['box'][1]
        if min(w,h)<3 or not 6<=max(w,h)<=160:continue
        txt=r['text'].strip()
        r['stratum']='symbol' if not txt else 'kana' if any('\u3040'<=v<='\u30ff' for v in txt) else 'numeric' if any(v.isdigit() for v in txt) else 'name'
        pool.append(r)
    con.close()
    old=read(ROOT/'evidence/contour-samples/dataset.json')
    oldlabels={r['id']:r['label'] for r in read(ROOT/'evidence/contour-samples/visual-labels.json')['labels']}
    known_ids={int(r['id']) for r in old}
    guard_data=read(ROOT/'evidence/noise-verifier/dataset.json')
    known_ids|={int(r['id']) for r in guard_data if str(r['id']).isdigit()}
    # Holdout selection is frozen first, before training positives or model fitting.
    hold=[];used=set();counts=Counter()
    def extract(r,split,index):
        a,b,c,d=r['box'];left=math.floor((a+c)/2)-96;top=math.floor((b+d)/2)-96
        im,_,sources=evidence_crop(ROOT/'data',{**r,'box':[left,top,left+192,top+192]},0)
        path=OUT/'crops'/f"{r['id']}.png";im.save(path)
        return {k:r[k] for k in ('id','source','z','x','y','box','stratum')} | dict(index=index,split=split,
            context=path.relative_to(ROOT).as_posix(),context_box=[a-left,b-top,c-left,d-top],context_sha256=sha(path),sources=sources)
    errors=[]
    for r in sorted(pool,key=lambda r:order(r['id'])):
        cap=24 if r['stratum']=='symbol' else 12
        if not reserved(r) or r['id'] in known_ids or counts[r['stratum']]>=cap or (r['x'],r['y']) in used:continue
        try:item=extract(r,'held-out',len(hold)+1)
        except (OSError,ValueError) as exc:errors.append(dict(id=r['id'],error=str(exc)));continue
        hold.append(item);counts[r['stratum']]+=1;used.add((r['x'],r['y']))
    write(OUT/'holdout-inputs.json',hold)
    base=[]
    for r in old:
        if r['split']!='development' or reserved(r) or any(near(r,t) for t in hold):continue
        lab=oldlabels[r['id']]
        base.append({k:r[k] for k in ('id','source','z','x','y','box','context_box','context_sha256')} |
          dict(context=(Path('evidence/contour-samples')/r['context']).as_posix(),label=lab,origin='contour-development',negative=lab=='contour-fragment'))
    new=[];used={(r['x'],r['y']) for r in base};counts=Counter()
    for r in sorted(pool,key=lambda r:order(r['id'])):
        if r['stratum']=='symbol' or reserved(r) or r['id'] in known_ids or any(near(r,t) for t in hold):continue
        if counts[r['stratum']]>=48 or (r['x'],r['y']) in used:continue
        try:item=extract(r,'development-protection',len(new)+1)
        except (OSError,ValueError) as exc:errors.append(dict(id=r['id'],error=str(exc)));continue
        new.append(item);counts[r['stratum']]+=1;used.add((r['x'],r['y']))
    write(OUT/'base-training.json',base);write(OUT/'new-protection-inputs.json',new)
    sheets(new,OUT,'protection')
    write(OUT/'selection.json',dict(seed=SEED,pool=len(pool),base=len(base),base_contours=sum(r['negative'] for r in base),
        new_protection=len(new),new_protection_strata=dict(counts),held_out=len(hold),
        held_out_strata=dict(Counter(r['stratum'] for r in hold)),errors=errors,
        rules='Shared cross-edition 4x4 block assignment; training excludes reserved blocks and two-tile neighborhoods of selected holdout contexts. One new crop per geographic tile. Holdout pixels not displayed or labelled.'))
    print(json.dumps(read(OUT/'selection.json'),indent=2))


if __name__=='__main__':main()
