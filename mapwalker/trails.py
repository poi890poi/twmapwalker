"""Propose aligned chains of ink dashes as trails; no map legend assumptions."""
import math
import cv2
import numpy as np


def trail_proposals(image, config):
    ink=(cv2.cvtColor(np.asarray(image),cv2.COLOR_RGB2GRAY)<config['ink_threshold']).astype(np.uint8)
    count,labels,stats,centers=cv2.connectedComponentsWithStats(ink,8)
    dashes=[]
    for i in range(1,count):
        x,y,w,h,area=map(int,stats[i])
        if not (4<=area<=220 and 3<=max(w,h)<=38):
            continue
        yy,xx=np.nonzero(labels[y:y+h,x:x+w]==i)
        points=np.column_stack((xx,yy)).astype(float)
        values,vectors=np.linalg.eigh(np.cov(points,rowvar=False))
        if values[1] < max(1,values[0]*3):
            continue
        dashes.append(dict(center=centers[i],axis=vectors[:,1],length=max(w,h),box=[x,y,x+w,y+h]))
    graph=[set() for _ in dashes]
    for i,a in enumerate(dashes):
        for j in range(i+1,len(dashes)):
            b=dashes[j];delta=b['center']-a['center'];distance=np.linalg.norm(delta)
            if not (4<distance<min(44,2*(a['length']+b['length'])+8)):
                continue
            direction=delta/distance
            if abs(direction@a['axis'])<0.82 or abs(direction@b['axis'])<0.82 or abs(a['axis']@b['axis'])<0.75:
                continue
            graph[i].add(j);graph[j].add(i)
    seen=set();result=[]
    for seed in range(len(dashes)):
        if seed in seen:
            continue
        stack=[seed];group=[];seen.add(seed)
        while stack:
            current=stack.pop();group.append(current)
            for neighbor in graph[current]:
                if neighbor not in seen:
                    seen.add(neighbor);stack.append(neighbor)
        if len(group)<3:
            continue
        centers=np.array([dashes[i]['center'] for i in group])
        # Principal ordering is a local segment only, not a claimed connected route.
        values,vectors=np.linalg.eigh(np.cov(centers,rowvar=False))
        if values[1]<values[0]*3:
            continue
        ordered=centers[np.argsort(centers@vectors[:,1])]
        span=float(np.linalg.norm(ordered[-1]-ordered[0]))
        if span<22:
            continue
        boxes=np.array([dashes[i]['box'] for i in group])
        box=[int(boxes[:,0].min()),int(boxes[:,1].min()),int(boxes[:,2].max()),int(boxes[:,3].max())]
        result.append(dict(kind='trail',text='',score=.40,box=box,repeating=False,
                           details=dict(method='aligned dash chain',dash_count=len(group),
                                        pixel_path=ordered.tolist(),interpretation='Candidate trail segment; continuity not established')))
    return result


def protect_trail_dashes(proposals, trails, shape):
    corridor=np.zeros(shape,np.uint8)
    for trail in trails:
        path=np.round(trail['details']['pixel_path']).astype(np.int32)
        cv2.polylines(corridor,[path],False,1,thickness=10)
    for p in proposals:
        x0,y0,x1,y1=p['box']
        x,y=int((x0+x1)/2),int((y0+y1)/2)
        p['details']['trail_context']=bool(corridor[min(y,shape[0]-1),min(x,shape[1]-1)])
    return proposals
