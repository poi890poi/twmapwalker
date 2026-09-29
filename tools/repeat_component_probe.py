"""Pixel-only component recurrence, experimental; no reference inputs."""
import cv2,numpy as np

def repeat_evidence(image,proposals):
    ink=(cv2.cvtColor(np.asarray(image),cv2.COLOR_RGB2GRAY)<135).astype('uint8')
    count,labels,stats,centers=cv2.connectedComponentsWithStats(ink,8)
    shapes=[]
    for i in range(1,count):
        x,y,w,h,a=stats[i]
        if not (15<=a<=300 and 5<=min(w,h) and max(w,h)<=45):continue
        shape=cv2.resize((labels[y:y+h,x:x+w]==i).astype('uint8'),(24,24),interpolation=cv2.INTER_NEAREST).astype(bool)
        shapes.append((int(i),shape))
    repeats=[]
    for i,a in shapes:
        peers=[];x,y,w,h,_=stats[i]
        for j,b in shapes:
            _,_,w2,h2,_=stats[j]
            if not (.75<=w/w2<=1.25 and .75<=h/h2<=1.25):continue
            if (a&b).sum()/max(1,(a|b).sum())>=.70:peers.append(j)
        if len(peers)<4:continue
        eig=np.linalg.eigvalsh(np.cov(centers[peers],rowvar=False))
        if eig[0]/max(1,eig[1])>=.15:repeats.append((i,peers))
    output=[]
    for p in proposals:
        x0,y0,x1,y1=p['box'];cx=(x0+x1)/2;cy=(y0+y1)/2;area=max(1,(x1-x0)*(y1-y0));matches=[]
        for i,peers in repeats:
            x,y,w,h,_=stats[i]
            if x-4<=cx<=x+w+4 and y-4<=cy<=y+h+4 and w*h/area>=.25:
                matches.append(dict(box=[int(x),int(y),int(x+w),int(y+h)],peers=[centers[j].tolist() for j in peers]))
        output.append({**p,'details':{**p['details'],'repeat_patch_texture':bool(matches),'repeated_components':matches}})
    return output
