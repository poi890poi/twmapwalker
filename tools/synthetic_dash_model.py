"""Synthetic-only dash likelihood; no OSM or user annotations enter this module."""
import math
import cv2
import numpy as np
from PIL import Image,ImageDraw,ImageFont
import torch
from torch import nn
import torch.nn.functional as F

SIZE=192

def sample(seed):
    r=np.random.default_rng(seed);n=288
    paper=float(r.uniform(190,250));yy,xx=np.mgrid[:n,:n]
    background=np.clip(paper+r.normal(0,r.uniform(1,5),(n,n))+(xx/n-.5)*r.uniform(-18,18),0,255).astype(np.uint8)
    ink=background.copy();target=np.zeros((n,n),np.uint8)
    amp=r.uniform(5,28);period=r.uniform(60,190);phase=r.uniform(0,6.3)
    for offset in np.arange(-60,n+60,r.uniform(9,22)):
        x=np.arange(n);y=offset+amp*np.sin(x/period*6.28+phase)+r.uniform(3,14)*np.sin(x/90+phase)
        p=np.column_stack((x,y)).astype(np.int32)
        cv2.polylines(ink,[p],False,int(r.uniform(30,140)),int(r.choice([1,2,2,3,4])),cv2.LINE_AA)
    # Printed marks and characters are negative examples.
    for _ in range(int(r.integers(0,25))):
        x,y=r.integers(0,n,2);radius=int(r.integers(2,5))
        if r.random()<.5:cv2.circle(ink,(int(x),int(y)),radius,int(r.uniform(30,100)),1,cv2.LINE_AA)
        else:
            for dx in (-3,0,3):cv2.line(ink,(int(x+dx),int(y)),(int(x+dx-2),int(y-5)),int(r.uniform(30,100)),1,cv2.LINE_AA)
    if r.random()<.7:
        im=Image.fromarray(ink);draw=ImageDraw.Draw(im)
        font=ImageFont.truetype('C:/Windows/Fonts/msjh.ttc',int(r.integers(12,38)))
        draw.text(tuple(r.integers(10,n-50,2)),r.choice(['溪山社','ウライ','文口','一二三','1200','800']),font=font,fill=int(r.uniform(10,90)))
        ink=np.asarray(im).copy()
    for _ in range(int(r.choice([0,1,1,1,2]))):
        theta=r.uniform(0,math.pi);t=np.arange(-n,n,.6)
        bend=r.uniform(8,40)*np.sin(t/r.uniform(50,140)+r.uniform(0,6.3))
        cx,cy=r.uniform(n*.3,n*.7,2)
        coords=np.column_stack((cx+t*np.cos(theta)-bend*np.sin(theta),cy+t*np.sin(theta)+bend*np.cos(theta)))
        arc=np.r_[0,np.cumsum(np.linalg.norm(np.diff(coords,axis=0),axis=1))]
        dash,gap=r.uniform(5,15),r.uniform(4,10);active=((arc+r.uniform(0,20))%(dash+gap))<dash
        width=int(r.choice([2,2,3,3,4]));color=int(r.uniform(10,100))
        for i in range(1,len(coords)):
            if active[i] and active[i-1]:
                a,b=tuple(coords[i-1].astype(int)),tuple(coords[i].astype(int))
                cv2.line(ink,a,b,color,width,cv2.LINE_AA);cv2.line(target,a,b,255,width,cv2.LINE_8)
    # Rotation changes the entire map, including crossings and text.
    matrix=cv2.getRotationMatrix2D((n/2,n/2),float(r.uniform(0,360)),float(r.uniform(.85,1.15)))
    ink=cv2.warpAffine(ink,matrix,(n,n),borderValue=paper)
    target=cv2.warpAffine(target,matrix,(n,n),flags=cv2.INTER_NEAREST)
    ink=cv2.GaussianBlur(ink,(3,3),float(r.uniform(.2,.8)))
    sl=slice(48,48+SIZE)
    return ink[sl,sl],target[sl,sl]>127

def block(a,b):return nn.Sequential(nn.Conv2d(a,b,3,padding=1),nn.GroupNorm(4,b),nn.SiLU(),nn.Conv2d(b,b,3,padding=1),nn.GroupNorm(4,b),nn.SiLU())

class DashNet(nn.Module):
    def __init__(self):
        super().__init__();self.a=block(1,12);self.b=block(12,24);self.c=block(24,48);self.d=block(72,24);self.e=block(36,12);self.out=nn.Conv2d(12,1,1)
    def forward(self,x):
        a=self.a(x);b=self.b(F.avg_pool2d(a,2));c=self.c(F.avg_pool2d(b,2))
        d=self.d(torch.cat((F.interpolate(c,size=b.shape[-2:],mode='bilinear',align_corners=False),b),1))
        e=self.e(torch.cat((F.interpolate(d,size=a.shape[-2:],mode='bilinear',align_corners=False),a),1))
        return self.out(e)

def infer(model,gray):
    h,w=gray.shape;total=np.zeros((h,w),np.float32);weight=np.zeros_like(total)
    for y in sorted(set(list(range(0,h-255,192))+[h-256])):
        for x in sorted(set(list(range(0,w-255,192))+[w-256])):
            patch=torch.from_numpy(gray[y:y+256,x:x+256].copy()).float()[None,None].cuda()/255
            with torch.inference_mode():p=model(patch).sigmoid()[0,0].cpu().numpy()
            window=np.outer(np.hanning(256),np.hanning(256)).astype(np.float32)+.01
            total[y:y+256,x:x+256]+=p*window;weight[y:y+256,x:x+256]+=window
    return total/weight

def connect(prob):
    """Short-gap links between predicted dash components; no route prior."""
    mask=(prob>=.5).astype(np.uint8)
    count,labels,stats,centers=cv2.connectedComponentsWithStats(mask,8);nodes=[]
    for i in range(1,count):
        x,y,w,h,area=map(int,stats[i])
        if not (5<=area<=600 and 3<=max(w,h)<=65):continue
        yy,xx=np.nonzero(labels[y:y+h,x:x+w]==i);pts=np.column_stack((xx,yy)).astype(float)
        vals,vec=np.linalg.eigh(np.cov(pts,rowvar=False))
        if vals[1]<max(1,2*vals[0]):continue
        nodes.append(dict(center=centers[i],axis=vec[:,1],size=max(w,h),label=i))
    graph=[set() for _ in nodes]
    for i,a in enumerate(nodes):
        sides={-1:[],1:[]}
        for j,b in enumerate(nodes):
            if i==j:continue
            delta=b['center']-a['center'];dist=np.linalg.norm(delta)
            if not (4<dist<=32):continue
            direction=delta/dist
            if abs(direction@a['axis'])<.75 or abs(direction@b['axis'])<.75:continue
            side=1 if delta@a['axis']>=0 else -1;sides[side].append((dist,j))
        graph[i]={min(v)[1] for v in sides.values() if v}
    mutual=[{j for j in ns if i in graph[j]} for i,ns in enumerate(graph)]
    from trail_graph_candidate import edge_paths
    paths=[];keep=np.zeros_like(mask)
    for chain in edge_paths(mutual):
        pts=np.array([nodes[i]['center'] for i in chain]);length=float(np.linalg.norm(np.diff(pts,axis=0),axis=1).sum())
        if len(chain)<5 or length<70 or chain[0]==chain[-1]:continue
        for i in chain:keep[labels==nodes[i]['label']]=1
        paths.append(dict(points=pts.tolist(),length_px=length,dashes=len(chain)))
    return keep,paths
