"""Template-free junction proposals for marks connected to long contour components."""
import cv2
import numpy as np


def junction_proposals(image, config):
    ink=(cv2.cvtColor(np.asarray(image),cv2.COLOR_RGB2GRAY)<config['ink_threshold']).astype(np.uint8)
    count,labels,stats,_=cv2.connectedComponentsWithStats(ink,8)
    large=np.zeros_like(ink)
    for i in range(1,count):
        if max(stats[i,2:4])>config['max_side']:
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
        if not changed:
            break
    p=np.pad(skel,1)
    ns=[p[:-2,1:-1],p[:-2,2:],p[1:-1,2:],p[2:,2:],p[2:,1:-1],p[2:,:-2],p[1:-1,:-2],p[:-2,:-2]]
    transitions=sum(((ns[i]==0)&(ns[(i+1)%8]==1)).astype(np.uint8) for i in range(8))
    branch=((skel==1)&(transitions>=3)).astype(np.uint8)
    clustered=cv2.dilate(branch,np.ones((11,11),np.uint8))
    count,labels,stats,_=cv2.connectedComponentsWithStats(clustered,8)
    proposals=[]
    for i in range(1,count):
        points=np.argwhere((labels==i)&(branch==1))
        if len(points)<2:
            continue
        y0,x0=points.min(0);y1,x1=points.max(0)
        if x1-x0>55 or y1-y0>55:
            continue
        box=[max(0,int(x0)-10),max(0,int(y0)-10),min(image.width,int(x1)+11),min(image.height,int(y1)+11)]
        proposals.append(dict(kind='symbol',text='',score=0.30,box=box,repeating=False,
                              details={'method':'junction cluster in long component',
                                       'junction_count':len(points),'position_quality':'local historical displacement unmeasured'}))
    return proposals
