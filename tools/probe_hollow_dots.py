"""Offline morphology experiment. Never imported by production; never writes labels.

Inputs are frozen annotations and content-addressed cached imagery. The shape
probe receives only pixels and the automatic box, not readings or classifications.
Run from the repository root with the project Python runtime.
"""
import argparse
import hashlib
import json
import math
import time
from pathlib import Path

import cv2
import numpy as np
from PIL import Image, ImageDraw

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / 'evidence/hollow-dot'
PARAMETERS = dict(thresholds=[120, 145, 170], hole_span=[5, 13], hole_area=[10, 100],
                  circularity=.60, aspect=.65, center_distance=9, maximum_box=60,
                  satellite_area=[2, 30], minimum_stable_thresholds=2)


def probe(image, box, satellite_max=30):
    """Broad ring baseline and conservative ring + lower stem + satellite probe."""
    gray = cv2.cvtColor(np.asarray(image), cv2.COLOR_RGB2GRAY)
    bx, by = (box[0]+box[2])/2, (box[1]+box[3])/2
    observations = []
    for threshold in PARAMETERS['thresholds']:
        ink = (gray < threshold).astype('uint8')
        contours, hierarchy = cv2.findContours(ink, cv2.RETR_CCOMP, cv2.CHAIN_APPROX_SIMPLE)
        _, labels, stats, centers = cv2.connectedComponentsWithStats(ink)
        hits = []
        for i, contour in enumerate(contours):
            if hierarchy[0][i][3] < 0:
                continue
            x, y, w, h = cv2.boundingRect(contour)
            area = cv2.contourArea(contour)
            perimeter = cv2.arcLength(contour, True)
            cx, cy = x+(w-1)/2, y+(h-1)/2
            if not (box[0] <= cx <= box[2] and box[1] <= cy <= box[3]):
                continue
            if not (5 <= min(w, h) <= max(w, h) <= 13 and 10 <= area <= 100
                    and min(w, h)/max(w, h) >= .65
                    and 4*math.pi*area/max(1, perimeter**2) >= .60):
                continue
            # Ring edge is ~2 pixels beyond the enclosed white region at z16.
            # Lower-center extension plus a separate nearby dot supports a tree.
            stem = ink[y+h+1:min(gray.shape[0], y+h+5), max(0,round(cx)-1):round(cx)+2]
            has_stem = stem.size > 0 and float(stem.mean()) >= .45
            satellites = []
            for stat, center in zip(stats[1:], centers[1:]):
                sx, sy = map(float, center)
                if (2 <= stat[cv2.CC_STAT_AREA] <= satellite_max and 3 <= abs(sx-cx) <= 14
                        and h/2+1 <= sy-cy <= h/2+12):
                    satellites.append([sx, sy])
            centered = math.hypot(cx-bx, cy-by) <= 9
            compact = max(box[2]-box[0], box[3]-box[1]) <= 60
            hits.append(dict(hole=[x,y,w,h], stem=has_stem, satellites=satellites,
                             conservative=bool(has_stem and satellites and centered and compact)))
        observations.append(dict(threshold=threshold, hits=hits))
    # Stability must concern the SAME hole, not unrelated holes at each threshold.
    stable = []
    for obs in observations:
        for hit in obs['hits']:
            if not hit['conservative']:
                continue
            x,y,w,h = hit['hole']; center = (x+w/2,y+h/2)
            support = sum(any(other['conservative'] and math.dist(center,
                (other['hole'][0]+other['hole'][2]/2,other['hole'][1]+other['hole'][3]/2)) <= 2
                for other in row['hits']) for row in observations)
            if support >= 2:
                stable.append(hit['hole'])
    return dict(ring_only=any(o['hits'] for o in observations),
                conservative=bool(stable), observations=observations)


def crop_cached(row):
    box = row['box']; cx=(box[0]+box[2])/2; cy=(box[1]+box[3])/2
    side=max(96, math.ceil(max(box[2]-box[0],box[3]-box[1]))+32)
    bounds=[round(256+cx-side/2),round(256+cy-side/2)]
    bounds += [bounds[0]+side,bounds[1]+side]
    canvas=Image.new('RGB',(768,768),'white'); provenance=[]
    for dy in (-1,0,1):
        for dx in (-1,0,1):
            if not (bounds[0] < (dx+2)*256 and bounds[2] > (dx+1)*256
                    and bounds[1] < (dy+2)*256 and bounds[3] > (dy+1)*256):
                continue
            folder=ROOT/'data/tiles/2026-09-28-v1'/row['source']/str(row['z'])/str(row['x']+dx)
            meta=json.loads((folder/f"{row['y']+dy}.json").read_text('utf-8'))
            path=folder/meta['file']; payload=path.read_bytes()
            assert hashlib.sha256(payload).hexdigest()==meta['sha256']
            canvas.paste(Image.open(path).convert('RGB'),((dx+1)*256,(dy+1)*256))
            provenance.append(dict(path=str(path.relative_to(ROOT)),sha256=meta['sha256']))
    local=[box[0]+256-bounds[0],box[1]+256-bounds[1],box[2]+256-bounds[0],box[3]+256-bounds[1]]
    return canvas.crop(bounds),local,provenance


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('--satellite-max',type=int,default=30)
    parser.add_argument('--output-stem',default='evaluation')
    args=parser.parse_args()
    rows=json.loads((OUT/'inputs.json').read_text('utf-8'))
    refs=json.loads((OUT/'visual-labels.json').read_text('utf-8'))
    samples=[]; images={}
    for row in rows:
        image,box,provenance=crop_cached(row)
        image.save(OUT/f"{row['id']}.png"); images[str(row['id'])]=image
        start=time.perf_counter(); result=probe(image,box,args.satellite_max); elapsed=(time.perf_counter()-start)*1000
        label=refs['labels'].get(str(row['id']),row['annotation']['classification'])
        samples.append(dict(id=str(row['id']),label=label,
            split='southern-check' if row['source']=='JM50K_1924_new' and row['y']>=28131 else 'development',
            source=row['source'],x=row['x'],y=row['y'],box=box,provenance=provenance,
            algorithm_ms=elapsed,**result))
    # Independent old user-identified marks, including hot spring, school, kana,
    # Chinese names and a useful numeric elevation. Images have a 64-pixel halo.
    manifest=json.loads((ROOT/'evidence/symbol-first/inputs.json').read_text('utf-8'))
    scenes={s['id']:s for s in manifest['scenes']}
    marks=json.loads((ROOT/'evidence/symbol-first/references.json').read_text('utf-8'))['marks']
    for n,ref in enumerate(marks):
        scene=scenes[ref['scene']]; path=ROOT/'evidence/symbol-first'/scene['path']
        assert hashlib.sha256(path.read_bytes()).hexdigest()==scene['sha256']
        im=Image.open(path).convert('RGB');box=ref['box']
        crop=[int(box[0])-20,int(box[1])-20,int(box[2])+20,int(box[3])+20]
        im=im.crop(crop);local=[box[0]-crop[0],box[1]-crop[1],box[2]-crop[0],box[3]-crop[1]]
        key=f'reference-{n}';images[key]=im;im.save(OUT/f'{key}.png')
        samples.append(dict(id=key,label='protected-reference',name=ref['label'],split='independent-reference',
            box=local,provenance=[dict(path=str(path.relative_to(ROOT)),sha256=scene['sha256'])],**probe(im,local,args.satellite_max)))
    counts={}
    for split in sorted({s['split'] for s in samples}):
        counts[split]={}
        for label in sorted({s['label'] for s in samples if s['split']==split}):
            selected=[s for s in samples if s['split']==split and s['label']==label]
            counts[split][label]=dict(total=len(selected),ring_only=sum(s['ring_only'] for s in selected),
                                      conservative=sum(s['conservative'] for s in selected))
    parameters={**PARAMETERS,'satellite_area':[2,args.satellite_max]}
    result=dict(parameters=parameters,inputs_sha256=hashlib.sha256((OUT/'inputs.json').read_bytes()).hexdigest(),
                harness_sha256=hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),counts=counts,samples=samples,
                decision='Research only. No production suppression. Insufficient independently labeled negatives.',
                limitations=['Southern check visually inspected before algorithm: not a blind or fresh holdout.',
                    'User Other is not a vegetation ground truth; morphology labels are assistant visual interpretation.',
                    'Duplicate detector findings can describe the same symbol; counts are findings, not independent objects.',
                    'Only already detected findings sampled; raw symbol/POI recall cannot be estimated.',
                    '23 user POI findings and 10 prior reference boxes cannot establish a very low false rejection rate.'])
    (OUT/f'{args.output_stem}.json').write_text(json.dumps(result,ensure_ascii=False,indent=2),'utf-8')
    selected=[s for s in samples if s['ring_only'] or s['label']=='protected-reference']
    canvas=Image.new('RGB',(1000,math.ceil(len(selected)/5)*224),'white');draw=ImageDraw.Draw(canvas)
    for n,s in enumerate(selected):
        x=n%5*200;y=n//5*224;im=images[s['id']].copy()
        scale=min(192/im.width,180/im.height)
        im=im.resize((round(im.width*scale),round(im.height*scale)),Image.Resampling.NEAREST)
        canvas.paste(im,(x,y+40))
        draw.text((x+3,y+3),s['id']+' '+s['label'],fill='black')
        draw.text((x+3,y+20),'ring + stem/dot' if s['conservative'] else 'ring only' if s['ring_only'] else 'retained',fill='black')
    canvas.save(OUT/f'{args.output_stem}-sheet.jpg')
    print(json.dumps(counts,indent=2))


if __name__=='__main__':
    main()
