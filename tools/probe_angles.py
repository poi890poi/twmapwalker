import json
import sys
from pathlib import Path
import numpy as np
from PIL import ImageDraw

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from mapwalker.detectors import CONFIG, TextDetector, filter_proposals
from mapwalker.paths import default_data
from mapwalker.sources import TileCache
from mapwalker.angled import angled_text_proposals

cache=TileCache(default_data());detector=TextDetector();rows=[]
for source in ('JM50K_1916','JM50K_1924_new'):
    for x,y in ((54895,28092),(54899,28096),(54896,28094),(54894,28089),(54898,28089)):
        im,manifest,_=cache.mosaic(source,16,x,y)
        base=filter_proposals(detector(im),np.zeros((384,384),bool),urban=False)
        extra=filter_proposals(angled_text_proposals(im,CONFIG,detector),np.zeros((384,384),bool),urban=False)
        rows.append(dict(source=source,x=x,y=y,baseline=base,angled=extra,inputs=manifest))
        print(source,x,y,json.dumps([dict(text=p['text'],angle=p['details']['angle_degrees_ccw'],score=round(p['score'],3)) for p in extra]),flush=True)
        draw=ImageDraw.Draw(im)
        for p in extra:
            draw.rectangle([v+64 for v in p['box']],outline='#167bba',width=2)
        im.save(ROOT/'evidence'/f'angled-{source}-{x}-{y}.jpg',quality=92)
(ROOT/'evidence'/'angled-text-probe.json').write_text(json.dumps(rows,ensure_ascii=False,indent=2),'utf-8')
