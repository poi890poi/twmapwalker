"""One-variable trial: add degraded contour/hatch negative appearances."""
import cv2,numpy as np
from synthetic_dash_model import sample as clean_sample

def sample(seed):
    image,target=clean_sample(seed);r=np.random.default_rng(seed+730000);h,w=image.shape
    paper=float(np.percentile(image,90));ink=np.maximum(0,paper-image.astype(float))
    # Irregular light breaks and printing-density fluctuations affect all ink.
    spots=cv2.GaussianBlur(r.random((h,w)).astype(np.float32),(0,0),.7)
    strength=np.clip((spots-.48)*7,0,.9)
    worn=np.clip(paper-ink*(1-strength),0,255).astype(np.uint8)
    visible=target & ((paper-worn)>15)
    # Cliff-like combs are negatives; avoid overwriting known generated trails.
    if r.random()<.65:
        hatch=np.zeros((h,w),np.uint8);theta=float(r.uniform(0,6.28));origin=r.uniform(20,170,2)
        tangent=np.array([np.cos(theta),np.sin(theta)]);normal=np.array([-tangent[1],tangent[0]])
        for t in np.arange(-110,110,5):
            a=origin+t*tangent+normal*float(10*np.sin(t/40));b=a+normal*r.uniform(6,20)
            cv2.line(hatch,tuple(a.astype(int)),tuple(b.astype(int)),255,int(r.choice([1,2])),cv2.LINE_AA)
        safe=cv2.dilate(target.astype(np.uint8),np.ones((7,7),np.uint8))==0
        use=(hatch>0)&safe;worn[use]=np.minimum(worn[use],r.integers(25,100))
    return worn,visible
