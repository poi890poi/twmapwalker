"""Record a user-supplied vertical-text example without inserting its reading into detections."""
import json
import sys
from pathlib import Path
import cv2
import numpy as np

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from mapwalker.detectors import TextDetector, specs
from mapwalker.paths import default_data
from mapwalker.sources import TileCache

cache=TileCache(default_data())
engine=TextDetector().engine
im,manifest,_=cache.mosaic('JM50K_1924_new',16,54896,28092)
im.save(ROOT/'evidence'/'vertical-label-source.png')
records=[]
for rotation in (0,90,270):
    rotated=im.rotate(rotation,expand=True).resize((768,768))
    output,timing=engine(cv2.cvtColor(np.asarray(rotated),cv2.COLOR_RGB2BGR))
    records.append(dict(rotation=rotation,raw_output=output,timing=timing))
record=dict(user_reference='ウライ社',role='evaluation only; user reading not fed to OCR',
            context='Centered on the adjacent tile to avoid evaluating a label only at the image edge',
            source_inputs=manifest,algorithm=next(s for s in specs() if s['name']=='text'),experiments=records)
(ROOT/'evidence'/'vertical-label-probe.json').write_text(json.dumps(record,ensure_ascii=False,indent=2),'utf-8')
print(json.dumps(records,ensure_ascii=True))
