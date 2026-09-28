import json
import sys
from pathlib import Path
import numpy as np
from PIL import ImageDraw

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from mapwalker.detectors import CONFIG, TextDetector, filter_proposals, specs
from mapwalker.paths import default_data
from mapwalker.sources import TileCache
from mapwalker.angled import angled_text_proposals

im,manifest,_=TileCache(default_data()).mosaic('JM50K_1924_new',16,54895,28091)
engine=TextDetector();mask=np.zeros((384,384),bool)
baseline=filter_proposals(engine(im),mask,urban=False)
candidate=filter_proposals(angled_text_proposals(im,CONFIG,engine),mask,urban=False)
record=dict(user_reference='溪',reference_role='user-identified development example; not runtime input',
            source='JM50K_1924_new',z=16,x=54895,y=28091,inputs=manifest,
            baseline=baseline,candidate=candidate,
            algorithm=next(s for s in specs() if s['name']=='angled-text'))
(ROOT/'evidence'/'skewed-creek-probe.json').write_text(json.dumps(record,ensure_ascii=False,indent=2),'utf-8')
draw=ImageDraw.Draw(im)
for p in candidate:
    points=[tuple(v) for v in p['details']['polygon']];draw.line(points+[points[0]],fill='#127ab6',width=3)
im.save(ROOT/'evidence'/'skewed-creek-probe.png')
print(json.dumps(dict(baseline=[p['text'] for p in baseline],angled=[(p['text'],p['details']['angle_degrees_ccw']) for p in candidate]),ensure_ascii=True))
