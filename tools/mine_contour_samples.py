"""Mine real detector mistakes for visual labelling; never assign a noise label."""
import hashlib
import json
import math
import sqlite3
from collections import Counter
from pathlib import Path

from PIL import Image, ImageDraw
from mapwalker.display import priority
from mapwalker.reading_suggestions import evidence_crop

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT/'evidence/contour-samples'
PRIOR = ['noise-verifier/dataset.json','noise-verifier/fresh/dataset.json',
         'native-patterns/fresh/dataset.json','vegetation-components/fresh/dataset.json',
         'vegetation-components/fresh-v2/dataset.json','symbol-first/inputs.json']
SEED = 'contour-mining-20261003-v1'


def digest(payload):
    return hashlib.sha256(payload).hexdigest()


def write(name, value):
    (OUT/name).write_text(json.dumps(value,ensure_ascii=False,indent=2)+'\n',encoding='utf8')


def sheet(rows, number):
    board = Image.new('RGB',(1200,1280),'white'); draw=ImageDraw.Draw(board)
    for i,row in enumerate(rows):
        x=i%4*300;y=i//4*320
        with Image.open(OUT/row['context']) as source:
            im=source.copy();ImageDraw.Draw(im).rectangle(row['context_box'],outline='#e02020',width=1)
            board.paste(im.resize((288,288),Image.Resampling.NEAREST),(x+6,y+29))
        draw.text((x+6,y+3),f"{row['index']:03}  POI {row['id']}  {row['source'].split('_')[1]}  {row['stratum']}",fill='black')
    board.save(OUT/f'development-{number:02}.jpg',quality=94)


def main():
    if (OUT/'dataset.json').exists():raise RuntimeError('Preserve the frozen dataset')
    OUT.mkdir(exist_ok=True);(OUT/'crops').mkdir(exist_ok=True)
    old=[];prior_hashes={}
    for name in PRIOR:
        path=ROOT/'evidence'/name;data=json.loads(path.read_text(encoding='utf8'))
        old.extend(data.get('scenes',[]) if isinstance(data,dict) else data)
        prior_hashes[name]=digest(path.read_bytes())
    old_tiles={(r['x']+dx,r['y']+dy) for r in old if r.get('z')==16 and 'x' in r
               for dx in range(-2,3) for dy in range(-2,3)}
    db=sqlite3.connect('file:'+str(ROOT/'data/mapwalker.sqlite3').replace('\\','/')+'?mode=ro',uri=True)
    db.row_factory=sqlite3.Row
    pool=[]
    for row in db.execute('''SELECT p.id,p.kind,p.text,p.score,p.box,p.details,t.source,t.z,t.x,t.y,a.spec,j.manifest
        FROM pois p JOIN jobs j ON j.id=p.job_id JOIN tiles t ON t.id=j.tile_id
        JOIN algorithms a ON a.fingerprint=j.algorithm
        WHERE a.active=1 AND j.state='complete' AND p.disposition='candidate' AND p.kind='symbol' AND t.z=16'''):
        r=dict(row)
        for key in ('box','details','spec','manifest'):r[key]=json.loads(r[key])
        # Interior tiles leave a two-tile gap between different 4x4 blocks.
        if r['x']%4 not in (1,2) or r['y']%4 not in (1,2):continue
        w,h=r['box'][2]-r['box'][0],r['box'][3]-r['box'][1]
        if min(w,h)<3 or max(w,h)>96 or max(w,h)<20:continue
        r['priority']=round(priority(r),6)
        r['stratum']='junction' if 'junction_count' in r['details'] else 'top' if r['priority']>=.74 else 'thin'
        # No labels or classifier scores determine selection or split.
        block=(r['x']//4,r['y']//4)
        r['block']=f'{block[0]}:{block[1]}'
        held=int(digest(f'{SEED}:split:{r["block"]}'.encode())[:8],16)%4==0
        r['split']='reserved-evaluation' if held else 'development'
        if held and (r['x'],r['y']) in old_tiles:continue
        r['order']=digest(f'{SEED}:sample:{r["id"]}'.encode())
        pool.append(r)
    db.close()
    quotas={'development':{'top':64,'thin':16,'junction':16},'reserved-evaluation':{'top':16,'thin':8,'junction':8}}
    used_tiles=set();blocks=Counter();counts=Counter();rows=[];errors=[]
    # Balance map edition and proposal family. Never sample both editions at one tile.
    for r in sorted(pool,key=lambda r:r['order']):
        key=(r['split'],r['source'],r['stratum']);tile=(r['x'],r['y'])
        if counts[key]>=quotas[r['split']][r['stratum']] or tile in used_tiles or blocks[r['block']]>=4:continue
        b=r['box'];cx=(b[0]+b[2])/2;cy=(b[1]+b[3])/2
        left=math.floor(cx)-96;top=math.floor(cy)-96
        item={**r,'box':[left,top,left+192,top+192]}
        try:im,_,provenance=evidence_crop(ROOT/'data',item,0)
        except (OSError,ValueError) as exc:
            errors.append(dict(id=r['id'],error=str(exc)));continue
        context=f'crops/{r["id"]}-context.png';im.save(OUT/context)
        local=[b[0]-left,b[1]-top,b[2]-left,b[3]-top]
        mark=im.crop((math.floor(local[0])-4,math.floor(local[1])-4,math.ceil(local[2])+4,math.ceil(local[3])+4))
        mark_path=f'crops/{r["id"]}-mark.png';mark.save(OUT/mark_path)
        rows.append({k:r[k] for k in ('id','source','z','x','y','box','priority','stratum','block','split')} |
                    dict(label='unreviewed',context=context,context_box=local,mark=mark_path,
                         context_sha256=digest((OUT/context).read_bytes()),mark_sha256=digest((OUT/mark_path).read_bytes()),
                         sources=provenance))
        used_tiles.add(tile);blocks[r['block']]+=1;counts[key]+=1
    rows.sort(key=lambda r:(r['split'],r['source'],r['stratum'],r['id']))
    for i,r in enumerate(rows):r['index']=i+1
    development=[r for r in rows if r['split']=='development']
    for start in range(0,len(development),16):sheet(development[start:start+16],start//16)
    write('dataset.json',rows)
    write('selection.json',dict(seed=SEED,pool=len(pool),counts={':'.join(k):v for k,v in counts.items()},
        prior_hashes=prior_hashes,missing_context=errors,blocks=len(blocks),tiles=len(used_tiles),
        rules='Active z16 symbol proposals, 20–96px extent; interior tiles of 4x4 geographic blocks; block split shared across editions; at most one sample per geographic tile and four per block; reserved areas exclude two-tile neighborhoods of listed prior studies. No inference labels.',
        limitations='Enriched detector-proposal sample, not a representative contour or POI dataset. Reserved pixels are frozen but not reviewed or used for training. Prior research exposure outside listed studies is not exhaustively known.'))
    print(json.dumps(dict(samples=len(rows),development=len(development),reserved=len(rows)-len(development),pool=len(pool),blocks=len(blocks),counts={':'.join(k):v for k,v in counts.items()}),indent=2))


if __name__=='__main__':main()
