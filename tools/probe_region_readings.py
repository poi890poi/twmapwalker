"""Offline second-pass OCR trial; user readings are evaluation only."""
import hashlib
import json
import sys
import time
from pathlib import Path

import cv2
import numpy as np
from PIL import Image

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from mapwalker.detectors import TextDetector
from tools.probe_hollow_dots import crop_cached


def main():
    out=ROOT/'evidence/multi-evidence'
    labels=json.loads((out/'evaluation-labels.json').read_text('utf-8'))
    rows=json.loads((out/'inputs.json').read_text('utf-8'))
    # Freeze the sample by IDs, never by desired readings or OSM identity.
    selected=[r for r in rows if str(r['id']) in labels]
    engine=TextDetector();results=[]
    for row in selected:
        image,box,provenance=crop_cached(row)
        x0,y0,x1,y1=box
        # Keep the complete existing region plus 8 pixels; no modern coordinates.
        patch=image.crop((int(x0)-8,int(y0)-8,int(x1)+8,int(y1)+8))
        result=[];start=time.perf_counter()
        for angle in (0,90,180,270):
            rotated=patch.rotate(angle,expand=True,fillcolor='white')
            for p in engine(rotated):
                result.append(dict(text=p['text'],score=p['score'],angle=angle,box=p['box']))
        results.append(dict(id=row['id'],readings=result,ms=(time.perf_counter()-start)*1000,
                            pixels=provenance))
    import rapidocr_onnxruntime
    models={p.name:hashlib.sha256(p.read_bytes()).hexdigest() for p in
            (Path(rapidocr_onnxruntime.__file__).parent/'models').glob('*.onnx')}
    (out/'region-readings.json').write_text(json.dumps(dict(models=models,rows=results),ensure_ascii=False,indent=2),'utf-8')
    for r in results:
        print(r['id'],labels[str(r['id'])]['classification'],labels[str(r['id'])]['ground_truth'],
              [(v['text'],round(v['score'],2),v['angle']) for v in r['readings']])


if __name__=='__main__':main()
