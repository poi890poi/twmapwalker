"""Frozen offline comparisons. References are never loaded by scene inference."""
import argparse
import hashlib
import json
import math
import re
import sys
import time
from pathlib import Path

import cv2
import numpy as np
from PIL import Image, ImageDraw

ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
OUT=ROOT/'evidence/detection-proposals'
from tools.detection_proposal_suite import save
from tools.layout_candidate import groups
from mapwalker.reading_suggestions import overlaps,unrotate_box

PARAMETERS=dict(angles=[0,90,180,270],score=.65,number_pattern=r'[0-9]{2,5}(?:[.,][0-9]+)?[.,]?',
    paddings=[8,64],agreement_rotations=2,ring_thresholds=[120,145,170],ring_neighbors=3,ring_radius=80,
    coverage=.8,iou=.5,owner_rule='proposal center inside [256,256,512,512); groups evaluated throughout scene',
    group_reading='upright member crops with pad8; concatenate along dominant axis both orders, minimum member score; no lexicon',
    evidence_reading='frozen pad64 number suggestions plus Japanese pad8 Kana at >=.65; append, never replace original')

def sha(path):return hashlib.sha256(path.read_bytes()).hexdigest()
def load(path):return json.loads(path.read_text('utf-8'))
def owner(p):
    a,b,c,d=p['box'];return 256<=(a+c)/2<512 and 256<=(b+d)/2<512
def crop(im,box,pad):
    bounds=[math.floor(box[0])-pad,math.floor(box[1])-pad,math.floor(box[2])+pad,math.floor(box[3])+pad]
    return im.crop(bounds),[box[0]-bounds[0],box[1]-bounds[1],box[2]-bounds[0],box[3]-bounds[1]]
def recognize(engine,im,angles=(0,90,180,270)):
    values=[]
    for angle in angles:
        patch=im.rotate(angle,expand=True,fillcolor='white')
        rows,_=engine(np.asarray(patch)[:,:,::-1].copy(),use_det=False,use_cls=False)
        values.extend(dict(text=text,score=float(score),angle=angle) for text,score in rows or [])
    return values
def numbers(detector,im,box):
    values=[]
    for angle in PARAMETERS['angles']:
        for r in detector(im.rotate(angle,expand=True,fillcolor='white')):
            mapped=unrotate_box(r['box'],angle,*im.size)
            if r['score']>=.65 and re.fullmatch(PARAMETERS['number_pattern'],r['text']) and overlaps(mapped,box):
                values.append(dict(text=r['text'],score=r['score'],angle=angle,box=mapped))
    return sorted(values,key=lambda r:-r['score'])
def geometry(split):
    target=OUT/f'{split}-geometry.json'
    if target.exists():raise RuntimeError('Already frozen')
    scenes=[]
    for s in load(OUT/f'{split}-inputs.json'):
        start=time.perf_counter();gs=groups(s['proposals']);ms=(time.perf_counter()-start)*1000
        for n,g in enumerate(gs):g['id']=f"{s['id']}-g{n}"
        scenes.append(dict(id=s['id'],groups=gs,ms=ms))
        im=Image.open(OUT/s['path']).convert('RGB');draw=ImageDraw.Draw(im)
        draw.rectangle(s['scored_owner_box'],outline='blue',width=2)
        for n,g in enumerate(gs):draw.rectangle(g['box'],outline='red',width=2);draw.text(g['box'][:2],f'G{n}',fill='red')
        im.save(OUT/f"{s['id']}-groups.png")
    save(target,scenes);print(split,'groups',sum(len(s['groups']) for s in scenes),flush=True)
def readings(split):
    target=OUT/f'{split}-readings.json'
    if target.exists():raise RuntimeError('Already frozen')
    from rapidocr_onnxruntime import RapidOCR
    from mapwalker.detectors import TextDetector
    start=time.perf_counter()
    engines={m:RapidOCR(**dict(intra_op_num_threads=2,inter_op_num_threads=1,text_score=0,
        **({'rec_model_path':str(ROOT/'data/reading-models/japan_PP-OCRv4_rec_mobile.onnx')} if m=='japanese' else {}))) for m in ('chinese','japanese')}
    detector=TextDetector();init=time.perf_counter()-start;rows=[]
    geos={s['id']:s['groups'] for s in load(OUT/f'{split}-geometry.json')}
    for s in load(OUT/f'{split}-inputs.json'):
        assert sha(OUT/s['path'])==s['sha256'];im=Image.open(OUT/s['path']).convert('RGB')
        for p in [p for p in s['proposals'] if owner(p)]:
            result=dict(scene=s['id'],id=str(p['id']),box=p['box'],kind='automatic',models={},numbers={},ms={})
            patch,local=crop(im,p['box'],8)
            for m,engine in engines.items():
                start=time.perf_counter();result['models'][m]=recognize(engine,patch);result['ms'][m]=(time.perf_counter()-start)*1000
            for pad in PARAMETERS['paddings']:
                patch,local=crop(im,p['box'],pad);start=time.perf_counter()
                result['numbers'][str(pad)]=numbers(detector,patch,local);result['ms'][f'number{pad}']=(time.perf_counter()-start)*1000
            rows.append(result)
        for g in geos[s['id']]:
            boxes=g['details']['member_boxes'];axis=int((g['box'][3]-g['box'][1])>(g['box'][2]-g['box'][0]))
            boxes=sorted(boxes,key=lambda b:b[axis]+b[axis+2]);result=dict(scene=s['id'],id=g['id'],box=g['box'],kind='group',models={},ms={})
            for m,engine in engines.items():
                start=time.perf_counter();members=[recognize(engine,crop(im,b,8)[0],(0,)) for b in boxes]
                texts=[max(v,key=lambda r:r['score'],default=dict(text='',score=0)) for v in members]
                result['models'][m]=dict(members=members,readings=[dict(text=''.join(v['text'] for v in order),score=min(v['score'] for v in texts),order=name) for order,name in ((texts,'forward'),(texts[::-1],'reverse'))])
                result['ms'][m]=(time.perf_counter()-start)*1000
            rows.append(result)
        print(split,s['id'],len(rows),'completed',flush=True)
    import rapidocr_onnxruntime
    paths=list((Path(rapidocr_onnxruntime.__file__).parent/'models').glob('*.onnx'))+[ROOT/'data/reading-models/japan_PP-OCRv4_rec_mobile.onnx']
    save(target,dict(parameters=PARAMETERS,inputs_sha256=sha(OUT/f'{split}-inputs.json'),geometry_sha256=sha(OUT/f'{split}-geometry.json'),
        harness_sha256=sha(Path(__file__)),model_sha256={p.name:sha(p) for p in paths},init_s=init,rows=rows))

def ring_centers(im):
    gray=cv2.cvtColor(np.asarray(im),cv2.COLOR_RGB2GRAY);found=[]
    for threshold in PARAMETERS['ring_thresholds']:
        contours,hierarchy=cv2.findContours((gray<threshold).astype('uint8'),cv2.RETR_CCOMP,cv2.CHAIN_APPROX_SIMPLE)
        for i,c in enumerate(contours):
            if hierarchy[0][i][3]<0:continue
            x,y,w,h=cv2.boundingRect(c);area=cv2.contourArea(c);per=cv2.arcLength(c,True)
            center=[x+(w-1)/2,y+(h-1)/2]
            if 5<=min(w,h)<=max(w,h)<=13 and 10<=area<=100 and min(w,h)/max(w,h)>=.65 and 4*math.pi*area/max(1,per*per)>=.6:
                if not any(math.dist(center,q)<=2 for q in found):found.append(center)
    return found
def ring_result(im,box):
    centers=ring_centers(im);hits=[c for c in centers if box[0]<=c[0]<=box[2] and box[1]<=c[1]<=box[3]]
    enriched=[c for c in hits if sum(2<math.dist(c,q)<=80 for q in centers)>=3]
    return dict(ring_only=bool(hits),repeated=bool(enriched),hits=hits,repeated_hits=enriched,total_rings=len(centers))
def rings():
    from tools.probe_hollow_dots import crop_cached
    refs=load(ROOT/'evidence/hollow-dot/visual-labels.json')['labels'];rows=[]
    for p in load(ROOT/'evidence/hollow-dot/inputs.json'):
        a,b,c,d=p['box'];expanded={**p,'box':[a-80,b-80,c+80,d+80]}
        im,local,provenance=crop_cached(expanded);box=[local[0]+80,local[1]+80,local[2]-80,local[3]-80]
        start=time.perf_counter();result=ring_result(im,box)
        rows.append(dict(id=str(p['id']),label=refs.get(str(p['id']),p['annotation']['classification']),box=box,provenance=provenance,ms=(time.perf_counter()-start)*1000,**result))
        if result['repeated'] and rows[-1]['label']=='poi':
            draw=ImageDraw.Draw(im);draw.rectangle(box,outline='red',width=2);im.save(OUT/f"ring-protected-{p['id']}.png")
    scenes={s['id']:s for s in load(ROOT/'evidence/symbol-first/inputs.json')['scenes']}
    for i,ref in enumerate(load(ROOT/'evidence/symbol-first/references.json')['marks']):
        s=scenes[ref['scene']];path=ROOT/'evidence/symbol-first'/s['path'];assert sha(path)==s['sha256']
        im=Image.open(path).convert('RGB');rows.append(dict(id=f'reference-{i}',label='protected-reference',name=ref['label'],box=ref['box'],**ring_result(im,ref['box'])))
    counts={label:{'total':len(sub:=[r for r in rows if r['label']==label]),'ring_only':sum(r['ring_only'] for r in sub),'repeated':sum(r['repeated'] for r in sub)} for label in sorted({r['label'] for r in rows})}
    save(OUT/'rings.json',dict(parameters=PARAMETERS,rows=rows,counts=counts));print(json.dumps(counts),flush=True)

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('action',choices=['geometry','readings','rings','lock']);p.add_argument('split',nargs='?',default='development');a=p.parse_args()
    if a.action=='lock':
        target=OUT/'parameters.json'
        if target.exists():raise RuntimeError('Already locked')
        save(target,dict(parameters=PARAMETERS,source_sha256=sha(Path(__file__)),geometry_sha256=sha(ROOT/'tools/layout_candidate.py')))
    elif a.action=='rings':rings()
    else:globals()[a.action](a.split)
