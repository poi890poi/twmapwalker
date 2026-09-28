"""Additional text orientation passes with explicit inverse coordinate transforms."""
import math
import cv2
import numpy as np
from PIL import Image


def rotate_with_transform(image, angle):
    w,h=image.size
    transform=cv2.getRotationMatrix2D((w/2,h/2),angle,1.0)
    cosine,sine=abs(transform[0,0]),abs(transform[0,1])
    nw,nh=math.ceil(w*cosine+h*sine),math.ceil(h*cosine+w*sine)
    transform[0,2]+=nw/2-w/2
    transform[1,2]+=nh/2-h/2
    rotated=cv2.warpAffine(np.asarray(image),transform,(nw,nh),flags=cv2.INTER_CUBIC,borderValue=(255,255,255))
    return Image.fromarray(rotated),transform


def angled_text_proposals(image, config, detector):
    results=[]
    for angle in config['text_angles']:
        rotated,transform=rotate_with_transform(image,angle)
        inverse=cv2.invertAffineTransform(transform)
        for p in detector(rotated,config):
            x0,y0,x1,y1=p['box']
            polygon=np.array(p['details'].get('polygon',[[x0,y0],[x1,y0],[x1,y1],[x0,y1]]),np.float64)
            mapped=np.column_stack((polygon,np.ones(len(polygon))))@inverse.T
            center=mapped.mean(0)
            if not (0<=center[0]<image.width and 0<=center[1]<image.height):
                continue
            item={**p,'box':[float(mapped[:,0].min()),float(mapped[:,1].min()),float(mapped[:,0].max()),float(mapped[:,1].max())],
                  'details':{**p['details'],'angle_degrees_ccw':angle,'polygon':mapped.tolist()}}
            results.append(item)
    # Overlapping transcriptions across angle passes remain inspectable as alternatives.
    kept=[]
    for p in sorted(results,key=lambda p:p['score'],reverse=True):
        x0,y0,x1,y1=p['box']
        duplicate=None
        for q in kept:
            a,b,c,d=q['box']
            overlap=max(0,min(x1,c)-max(x0,a))*max(0,min(y1,d)-max(y0,b))
            union=(x1-x0)*(y1-y0)+(c-a)*(d-b)-overlap
            if overlap/max(1,union)>0.4:
                duplicate=q
                break
        if duplicate:
            duplicate['details'].setdefault('alternatives',[]).append(dict(text=p['text'],score=p['score'],angle=p['details']['angle_degrees_ccw']))
        else:
            kept.append(p)
    return kept
