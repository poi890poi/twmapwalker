"""Offline proposal experiments. Inputs and references are frozen separately."""
import argparse
import hashlib
import json
import math
import re
import sqlite3
import sys
import time
from pathlib import Path

import numpy as np
from PIL import Image,ImageDraw

ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
OUT=ROOT/'evidence/detection-proposals'


def save(path,value):
    path.write_text(json.dumps(value,ensure_ascii=False,indent=2),'utf-8')


def cached_scene(source,z,x,y):
    canvas=Image.new('RGB',(768,768),'white');manifest=[]
    for dy in (-1,0,1):
        for dx in (-1,0,1):
            folder=ROOT/'data/tiles/2026-09-28-v1'/source/str(z)/str(x+dx)
            record=json.loads((folder/f'{y+dy}.json').read_text('utf-8'))
            path=folder/record['file'];payload=path.read_bytes()
            if hashlib.sha256(payload).hexdigest()!=record['sha256']:raise ValueError('Pixel integrity failure')
            canvas.paste(Image.open(path).convert('RGB'),((dx+1)*256,(dy+1)*256));manifest.append(record)
    return canvas,manifest


def freeze(split):
    OUT.mkdir(exist_ok=True)
    target=OUT/f'{split}-inputs.json'
    if target.exists():raise RuntimeError('Inputs already frozen')
    db=sqlite3.connect(f'file:{ROOT/"data/mapwalker.sqlite3"}?mode=ro',uri=True);db.row_factory=sqlite3.Row
    rows=[dict(r) for r in db.execute('''SELECT p.id,p.kind,p.text,p.score,p.box,p.details,p.lon,p.lat,t.source,t.z,t.x,t.y,a.name algorithm
        FROM pois p JOIN jobs j ON j.id=p.job_id JOIN tiles t ON t.id=j.tile_id
        JOIN algorithms a ON a.fingerprint=j.algorithm WHERE a.active=1 AND j.state='complete' AND p.kind='text' ''')]
    for r in rows:
        for f in ('box','details'):r[f]=json.loads(r[f])
    if split=='development':
        ids=[14965,43405,45553,69139,70070,70486,68891,20592]
        selected=[next(r for r in rows if r['id']==i) for i in ids]
        selected.append(dict(id='wulai',source='JM50K_1924_new',z=16,x=54896,y=28092))
    else:
        # Select completed owner tiles, independent of OCR transcripts or labels.
        # Exclude every prior scene/crop tile and its immediate neighborhood.
        excluded=set()
        paths=[ROOT/'evidence/reading-improvements/inputs.json',ROOT/'evidence/reading-improvements/holdout-inputs.json',OUT/'development-inputs.json']
        for path in paths:
            for s in json.loads(path.read_text('utf-8')):
                if all(k in s for k in ('source','z','x','y')):excluded.add(tuple(s[k] for k in ('source','z','x','y')))
                for p in s.get('provenance',[]):
                    bits=Path(p.get('path','')).parts
                    if len(bits)>=6 and bits[0]=='data':
                        try:excluded.add((bits[3],int(bits[4]),int(bits[5]),int(Path(bits[6]).stem.split('-')[0])))
                        except (ValueError,IndexError):pass
        # Include earlier scene manifests without reading their evaluation labels.
        for folder in ('symbol-first','detection-round2','detection-round3','model-trials'):
            for path in (ROOT/'evidence'/folder).glob('*inputs.json'):
                data=json.loads(path.read_text('utf-8'));scenes=data.get('scenes',data.get('discovery',[])) if isinstance(data,dict) else data
                for s in scenes:
                    if all(k in s for k in ('source','z','x','y')):excluded.add(tuple(s[k] for k in ('source','z','x','y')))
        choices=sorted({tuple(r[k] for k in ('source','z','x','y')) for r in rows},key=lambda k:hashlib.sha256(('proposal-holdout-v1'+str(k)).encode()).hexdigest())
        selected=[]
        for source in ('JM50K_1916','JM50K_1924_new'):
            count=0
            for key in choices:
                if key[0]!=source:continue
                if any(key[:2]==e[:2] and abs(key[2]-e[2])<=1 and abs(key[3]-e[3])<=1 for e in excluded):continue
                try:cached_scene(*key)
                except (OSError,ValueError):continue
                selected.append(dict(zip(('source','z','x','y'),key),id=f'fresh-{len(selected)}'))
                excluded.add(key);count+=1
                if count==4:break
    scenes=[]
    for selected_row in selected:
        source,z,x,y=(selected_row[k] for k in ('source','z','x','y'));image,manifest=cached_scene(source,z,x,y)
        sid=f"{split}-{selected_row['id']}";path=OUT/f'{sid}.png';image.save(path)
        proposals=[]
        for r in rows:
            if r['source']!=source or r['z']!=z or abs(r['x']-x)>1 or abs(r['y']-y)>1:continue
            a,b,c,d=r['box'];dx=(r['x']-x+1)*256;dy=(r['y']-y+1)*256
            proposals.append({**r,'box':[a+dx,b+dy,c+dx,d+dy]})
        scenes.append(dict(id=sid,source=source,z=z,x=x,y=y,path=path.name,sha256=hashlib.sha256(path.read_bytes()).hexdigest(),
                           manifest=manifest,proposals=proposals,scored_owner_box=[256,256,512,512]))
    save(target,scenes)
    for offset in range(0,len(scenes),4):
        sheet=Image.new('RGB',(1560,1580),'white');draw=ImageDraw.Draw(sheet)
        for n,s in enumerate(scenes[offset:offset+4]):
            x=n%2*780;y=n//2*790;sheet.paste(Image.open(OUT/s['path']),(x,y+22));draw.text((x+5,y+3),s['id']+' '+s['source'],fill='black')
        sheet.save(OUT/f'{split}-contact-{offset//4}.png')
    print('Frozen',split,len(scenes),'scenes',sum(len(s['proposals']) for s in scenes),'stored proposals')


def freeze_numbers():
    """Additional positive-enriched check; raw OCR selection, no reference access."""
    target=OUT/'number-holdout-inputs.json'
    if target.exists():raise RuntimeError('Inputs already frozen')
    excluded=set()
    for folder in ('reading-improvements','detection-proposals','symbol-first','detection-round2','detection-round3','model-trials'):
        for path in (ROOT/'evidence'/folder).glob('*inputs.json'):
            def visit(value):
                if isinstance(value,dict):
                    if all(k in value for k in ('source','z','x','y')):excluded.add(tuple(value[k] for k in ('source','z','x','y')))
                    if isinstance(value.get('path'),str):
                        bits=Path(value['path']).parts
                        if len(bits)>=7 and bits[0]=='data':
                            try:excluded.add((bits[3],int(bits[4]),int(bits[5]),int(Path(bits[6]).stem.split('-')[0])))
                            except ValueError:pass
                    for v in value.values():visit(v)
                elif isinstance(value,list):
                    for v in value:visit(v)
            visit(json.loads(path.read_text('utf-8')))
    db=sqlite3.connect(f'file:{ROOT/"data/mapwalker.sqlite3"}?mode=ro',uri=True);db.row_factory=sqlite3.Row
    rows=[dict(r) for r in db.execute('''SELECT p.id,p.kind,p.text,p.score,p.box,p.details,p.lon,p.lat,t.source,t.z,t.x,t.y,a.name algorithm
        FROM pois p JOIN jobs j ON j.id=p.job_id JOIN tiles t ON t.id=j.tile_id
        JOIN algorithms a ON a.fingerprint=j.algorithm WHERE a.active=1 AND j.state='complete' AND p.kind='text' ''')]
    rows=sorted([r for r in rows if re.fullmatch(r'\d{2,5}(?:[.,]\d+)?[.,]?',r['text'])],key=lambda r:hashlib.sha256(('number-holdout-v1'+str(r['id'])).encode()).hexdigest())
    scenes=[]
    for source in ('JM50K_1916','JM50K_1924_new'):
        count=0
        for r in rows:
            key=tuple(r[k] for k in ('source','z','x','y'))
            if key[0]!=source or any(key[:2]==e[:2] and abs(key[2]-e[2])<=1 and abs(key[3]-e[3])<=1 for e in excluded):continue
            try:im,manifest=cached_scene(*key)
            except (OSError,ValueError):continue
            for field in ('box','details'):r[field]=json.loads(r[field])
            sid=f'number-holdout-{r["id"]}';path=OUT/f'{sid}.png';im.save(path)
            r['box']=[v+256 for v in r['box']]
            scenes.append(dict(id=sid,source=key[0],z=key[1],x=key[2],y=key[3],path=path.name,sha256=hashlib.sha256(path.read_bytes()).hexdigest(),manifest=manifest,proposals=[r],scored_owner_box=[256,256,512,512]))
            excluded.add(key);count+=1
            if count==4:break
    save(target,scenes);print('Frozen number positive-enriched holdout',len(scenes))


if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('action',choices=['freeze']);parser.add_argument('split',choices=['development','holdout','numbers']);args=parser.parse_args()
    freeze_numbers() if args.split=='numbers' else freeze(args.split)
