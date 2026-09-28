"""A single-variable recall experiment: propose junction clusters in large ink components.

Evaluation landmarks come from user-identified glyphs and visually located source pixels,
not the detector's output. These two examples are development probes, NOT a test set.
"""
import json
import sys
from pathlib import Path
import cv2
import numpy as np
from PIL import Image, ImageDraw

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from mapwalker.paths import default_data
from mapwalker.sources import TileCache
from mapwalker.detectors import CONFIG, symbol_proposals


def junctions(image):
    ink=(cv2.cvtColor(np.asarray(image),cv2.COLOR_RGB2GRAY)<CONFIG['ink_threshold']).astype(np.uint8)
    count,labels,stats,_=cv2.connectedComponentsWithStats(ink,8)
    large=np.zeros_like(ink)
    for i in range(1,count):
        if max(stats[i,2:4])>CONFIG['max_side']:
            large[labels==i]=1
    skel=large.copy()
    for _ in range(80):
        changed=0
        for phase in (0,1):
            p=np.pad(skel,1)
            ns=[p[:-2,1:-1],p[:-2,2:],p[1:-1,2:],p[2:,2:],p[2:,1:-1],p[2:,:-2],p[1:-1,:-2],p[:-2,:-2]]
            neighbors=sum(ns)
            transitions=sum(((ns[i]==0)&(ns[(i+1)%8]==1)).astype(np.uint8) for i in range(8))
            if phase==0:
                a=ns[0]*ns[2]*ns[4];b=ns[2]*ns[4]*ns[6]
            else:
                a=ns[0]*ns[2]*ns[6];b=ns[0]*ns[4]*ns[6]
            remove=(skel==1)&(neighbors>=2)&(neighbors<=6)&(transitions==1)&(a==0)&(b==0)
            changed+=int(remove.sum());skel[remove]=0
        if not changed:break
    p=np.pad(skel,1)
    ns=[p[:-2,1:-1],p[:-2,2:],p[1:-1,2:],p[2:,2:],p[2:,1:-1],p[2:,:-2],p[1:-1,:-2],p[:-2,:-2]]
    transitions=sum(((ns[i]==0)&(ns[(i+1)%8]==1)).astype(np.uint8) for i in range(8))
    branch=((skel==1)&(transitions>=3)).astype(np.uint8)
    clustered=cv2.dilate(branch,np.ones((11,11),np.uint8))
    count,labels,stats,centers=cv2.connectedComponentsWithStats(clustered,8)
    proposals=[]
    for i in range(1,count):
        points=np.argwhere((labels==i)&(branch==1))
        if len(points)<2:continue
        y0,x0=points.min(0);y1,x1=points.max(0)
        if x1-x0>55 or y1-y0>55:continue
        proposals.append([max(0,int(x0)-10),max(0,int(y0)-10),min(384,int(x1)+11),min(384,int(y1)+11)])
    return proposals


def main():
    cache=TileCache(default_data())
    historic,manifest,_=cache.mosaic('JM50K_1924_new',16,54895,28092)
    base=[p['box'] for p in symbol_proposals(historic)]
    extra=junctions(historic)
    # Owner-tile coordinates, manually read from original pixels.
    refs=[dict(name='school (user identifies 文)',box=[195,46,224,80]),
          dict(name='hot spring (user identifies symbol)',box=[94,120,137,156])]
    def matched(box,proposals):
        x0,y0,x1,y1=[v+64 for v in box]
        return any(max(0,min(x1,b[2])-max(x0,b[0]))*max(0,min(y1,b[3])-max(y0,b[1]))/
                   max(1,(x1-x0)*(y1-y0)+(b[2]-b[0])*(b[3]-b[1])-max(0,min(x1,b[2])-max(x0,b[0]))*max(0,min(y1,b[3])-max(y0,b[1])))>=0.15 for b in proposals)
    records=[]
    for ref in refs:records.append(dict(**ref,baseline_hit=matched(ref['box'],base),junction_hit=matched(ref['box'],extra)))
    image=historic.copy();draw=ImageDraw.Draw(image)
    for box in extra:draw.rectangle(box,outline='blue',width=2)
    for ref in refs:draw.rectangle([v+64 for v in ref['box']],outline='red',width=2)
    image.save(ROOT/'evidence'/'junction-experiment.png')
    payload=dict(references=records,baseline_proposals=len(base),extra_proposals=len(extra),
                 proposals=extra,source_inputs=manifest,
                 decision='Experimental only: evaluate counts and raw images; no overall accuracy claim')
    (ROOT/'evidence'/'junction-experiment.json').write_text(json.dumps(payload,indent=2),'utf-8')
    print(json.dumps(records), 'extra',len(extra))


if __name__=='__main__':main()
