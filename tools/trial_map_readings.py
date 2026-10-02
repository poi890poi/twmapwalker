"""Frozen recognition-only comparison; no annotations enter the reader."""
import argparse
import hashlib
import json
import math
import sys
import time
from pathlib import Path

import numpy as np
from PIL import Image

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from tools.probe_hollow_dots import crop_cached

OUT=ROOT/'evidence/reading-improvements'


def prepare():
    if (OUT/'inputs.json').exists():return
    labels=json.loads((ROOT/'evidence/multi-evidence/evaluation-labels.json').read_text('utf-8'))
    rows=json.loads((ROOT/'evidence/multi-evidence/inputs.json').read_text('utf-8'))
    samples=[]
    extra={8028,14949,33378,33517,43912,70483,78992,79056}
    for row in rows:
        if str(row['id']) not in labels and row['id'] not in extra:continue
        image,box,provenance=crop_cached(row)
        patch=image.crop((int(box[0])-8,int(box[1])-8,int(box[2])+8,int(box[3])+8))
        key=str(row['id']);patch.save(OUT/f'{key}.png')
        samples.append(dict(id=key,path=f'{key}.png',role='automatic-box',raw_text=row['text'],
                            source=row['source'],box=row['box'],provenance=provenance))
    refs=json.loads((ROOT/'evidence/symbol-first/references.json').read_text('utf-8'))['marks']
    scenes={s['id']:s for s in json.loads((ROOT/'evidence/symbol-first/inputs.json').read_text('utf-8'))['scenes']}
    for i,mark in enumerate(refs[:8]):
        scene=scenes[mark['scene']];path=ROOT/'evidence/symbol-first'/scene['path'];raw=path.read_bytes()
        assert hashlib.sha256(raw).hexdigest()==scene['sha256']
        image=Image.open(path).convert('RGB');box=mark['box']
        image.crop((box[0]-4,box[1]-4,box[2]+4,box[3]+4)).save(OUT/f'ref-{i}.png')
        samples.append(dict(id=f'ref-{i}',path=f'ref-{i}.png',role='manual-box-diagnostic',raw_text='',
                            provenance=[dict(path=str(path),sha256=scene['sha256'])]))
        labels[f'ref-{i}']=dict(ground_truth=mark['label'],classification='poi')
    for s in samples:s['sha256']=hashlib.sha256((OUT/s['path']).read_bytes()).hexdigest()
    (OUT/'inputs.json').write_text(json.dumps(samples,ensure_ascii=False,indent=2),'utf-8')
    (OUT/'labels.json').write_text(json.dumps(labels,ensure_ascii=False,indent=2),'utf-8')


def main():
    parser=argparse.ArgumentParser();parser.add_argument('model',choices=['chinese','japanese','english'])
    parser.add_argument('--padding',type=int,default=8,choices=[8,24,64])
    parser.add_argument('--detect',action='store_true');args=parser.parse_args()
    prepare()
    manifest=OUT/'inputs.json';suffix=''
    if args.padding!=8:
        suffix=f'-pad{args.padding}';manifest=OUT/f'inputs{suffix}.json'
        if not manifest.exists():
            rows={str(r['id']):r for r in json.loads((ROOT/'evidence/multi-evidence/inputs.json').read_text('utf-8'))}
            samples=json.loads((OUT/'inputs.json').read_text('utf-8'))
            for sample in samples:
                if sample['role']!='automatic-box':continue
                row=rows[sample['id']];box=row['box'];pad=args.padding
                bounds=[math.floor(box[0])-pad,math.floor(box[1])-pad,math.ceil(box[2])+pad,math.ceil(box[3])+pad]
                canvas=Image.new('RGB',(bounds[2]-bounds[0],bounds[3]-bounds[1]),'white');provenance=[]
                for dy in range(math.floor(bounds[1]/256),math.ceil(bounds[3]/256)):
                    for dx in range(math.floor(bounds[0]/256),math.ceil(bounds[2]/256)):
                        folder=ROOT/'data/tiles/2026-09-28-v1'/row['source']/str(row['z'])/str(row['x']+dx)
                        meta=json.loads((folder/f"{row['y']+dy}.json").read_text('utf-8'))
                        path=folder/meta['file'];payload=path.read_bytes()
                        assert hashlib.sha256(payload).hexdigest()==meta['sha256']
                        canvas.paste(Image.open(path).convert('RGB'),(dx*256-bounds[0],dy*256-bounds[1]))
                        provenance.append(dict(path=str(path.relative_to(ROOT)),sha256=meta['sha256']))
                sample['path']=f"{sample['id']}{suffix}.png";canvas.save(OUT/sample['path'])
                sample['sha256']=hashlib.sha256((OUT/sample['path']).read_bytes()).hexdigest()
                sample['provenance']=provenance
            manifest.write_text(json.dumps(samples,ensure_ascii=False,indent=2),'utf-8')
    from rapidocr_onnxruntime import RapidOCR
    params=dict(intra_op_num_threads=2,inter_op_num_threads=1,text_score=0)
    if args.model=='japanese':params['rec_model_path']=str(ROOT/'data/reading-trials/japan_PP-OCRv4_rec_mobile.onnx')
    if args.model=='english':params['rec_model_path']=str(ROOT/'data/reading-trials/en_PP-OCRv4_rec_mobile.onnx')
    start=time.perf_counter();engine=RapidOCR(**params);init=time.perf_counter()-start
    if args.detect:
        from mapwalker.detectors import TextDetector
        detector=TextDetector()
        if args.model!='chinese':
            params['text_score']=.45;detector.engine=RapidOCR(**params)
    samples=json.loads(manifest.read_text('utf-8'));rows=[]
    for sample in samples:
        path=OUT/sample['path'];assert hashlib.sha256(path.read_bytes()).hexdigest()==sample['sha256']
        image=Image.open(path).convert('RGB');readings=[];start=time.perf_counter()
        for angle in (0,90,180,270):
            patch=image.rotate(angle,expand=True,fillcolor='white')
            if args.detect:
                readings.extend(dict(text=r['text'],score=r['score'],angle=angle,box=r['box']) for r in detector(patch))
            else:
                result,_=engine(np.asarray(patch)[:,:,::-1].copy(),use_det=False,use_cls=False)
                readings.extend(dict(text=text,score=float(score),angle=angle) for text,score in result or [])
        rows.append(dict(id=sample['id'],readings=readings,ms=(time.perf_counter()-start)*1000))
    model_path=Path(engine.text_rec.session.session._model_path)
    output=dict(model=args.model,model_sha256=hashlib.sha256(model_path.read_bytes()).hexdigest(),init_s=init,
                input_sha256=hashlib.sha256(manifest.read_bytes()).hexdigest(),rows=rows)
    mode='-detect' if args.detect else ''
    (OUT/f'{args.model}{suffix}{mode}.json').write_text(json.dumps(output,ensure_ascii=False,indent=2),'utf-8')
    labels=json.loads((OUT/'labels.json').read_text('utf-8'))
    for row in rows:
        label=labels.get(row['id'],{}).get('ground_truth','')
        if label or row['id'].startswith('ref-'):
            print(row['id'],label,[(r['text'],round(r['score'],2),r['angle']) for r in row['readings']])


if __name__=='__main__':main()
