"""Group unread detections using geometry alone. No names or references."""
import math
import numpy as np
from mapwalker.region_model import iou

def groups(proposals):
    # Compact character-sized seeds; large connected contour regions cannot anchor.
    seeds=[]
    for p in sorted(proposals,key=lambda p:-p['score']):
        x0,y0,x1,y1=p['box'];w,h=x1-x0,y1-y0
        if min(w,h)<16 or max(w,h)>100 or max(w,h)>2.2*min(w,h):continue
        c=np.array([(x0+x1)/2,(y0+y1)/2]);size=math.sqrt(w*h)
        if any(np.linalg.norm(c-q['center'])<.42*min(size,q['size']) for q in seeds):continue
        seeds.append(dict(proposal=p,center=c,size=size))
    candidates={}
    for i,a in enumerate(seeds):
        for j,b in enumerate(seeds):
            if j<=i:continue
            delta=b['center']-a['center'];length=np.linalg.norm(delta)
            size=(a['size']+b['size'])/2
            if not .7*size<=length<=2.3*size:continue
            direction=delta/length;normal=np.array([-direction[1],direction[0]])
            members=[]
            for k,c in enumerate(seeds):
                if not .65<=c['size']/size<=1.55:continue
                v=c['center']-a['center'];across=abs(v@normal);along=float(v@direction)
                if across<=.22*size:members.append((along,k))
            members.sort();chains=[];chain=[]
            for t,k in members:
                if chain and not .65*size<=t-chain[-1][0]<=2.3*size:
                    chains.append(chain);chain=[]
                chain.append((t,k))
            chains.append(chain)
            for chain in chains:
                ids=tuple(k for _,k in chain)
                if len(ids)<3 or i not in ids or j not in ids:continue
                ps=[seeds[k]['proposal'] for k in ids]
                scores=[p['score'] for p in ps]
                gaps=np.diff([t for t,k in chain])
                if min(gaps)/max(gaps)<.6 or np.mean(scores)<.40 or max(scores)<.55:continue
                boxes=np.array([p['box'] for p in ps]);box=[float(boxes[:,0].min()),float(boxes[:,1].min()),float(boxes[:,2].max()),float(boxes[:,3].max())]
                key=tuple(sorted(ids));candidates[key]=dict(kind='text',text='',box=box,score=float(np.mean(scores)),repeating=False,details=dict(method='Sparse text layout',recognition='not attempted',member_boxes=[p['box'] for p in ps],member_scores=scores,member_count=len(ps),layout_angle=float(math.degrees(math.atan2(direction[1],direction[0]))),reading_candidates=[]))
    chosen=[];used=set()
    for ids,p in sorted(candidates.items(),key=lambda kv:(-len(kv[0]),-kv[1]['score'])):
        if used.intersection(ids):continue
        chosen.append(p);used.update(ids)
    return chosen
