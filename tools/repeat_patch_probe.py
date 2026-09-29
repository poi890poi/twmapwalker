"""Experimental pixel-only repetition evidence; never reads reference labels."""
import cv2
import numpy as np


def repeat_evidence(image, proposals):
    gray=cv2.cvtColor(np.asarray(image),cv2.COLOR_RGB2GRAY).astype(np.float32)/255
    detail=gray-cv2.GaussianBlur(gray,(0,0),3)
    output=[]
    for proposal in proposals:
        x0,y0,x1,y1=proposal['box']
        x0,y0=max(0,int(x0)+4),max(0,int(y0)+4)
        x1,y1=min(gray.shape[1],int(x1)-4),min(gray.shape[0],int(y1)-4)
        matches=[]
        if 12<=min(x1-x0,y1-y0) and max(x1-x0,y1-y0)<=80:
            template=detail[y0:y1,x0:x1]
            scores=cv2.matchTemplate(detail,template,cv2.TM_CCOEFF_NORMED)
            for _ in range(16):
                _,peak,_,point=cv2.minMaxLoc(scores)
                if peak<.80:break
                x,y=point;cx=x+template.shape[1]/2;cy=y+template.shape[0]/2
                matches.append([cx,cy,float(peak)])
                rx=max(8,template.shape[1]);ry=max(8,template.shape[0])
                scores[max(0,y-ry):y+ry+1,max(0,x-rx):x+rx+1]=-1
        spread=0
        if len(matches)>=4:
            eig=np.linalg.eigvalsh(np.cov(np.array(matches)[:,:2],rowvar=False))
            spread=float(eig[0]/max(1,eig[1]))
        output.append({**proposal,'details':{**proposal['details'],
            'repeat_patch_count':len(matches),'repeat_patch_matches':matches,
            'repeat_patch_spread':spread,'repeat_patch_texture':len(matches)>=4 and spread>=.15}})
    return output
