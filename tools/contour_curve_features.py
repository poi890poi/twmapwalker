"""Explain target ink with curves inferred only from surrounding map pixels."""
import math
import cv2
import numpy as np
from PIL import Image

from .contour_topology_trial import thin

PARAMETERS=dict(ink_background_sigma=8,ink_contrast=18/255,target_exclusion_halo=4,
    minimum_chain_nodes=20,neighbor_span_margin=8,neighbor_fit_rms_max=2.5,
    minimum_neighbor_chains=2,neighbor_shape_deviation_max=6,
    anchor_strip_pixels=[3,15],anchor_match_tolerance=3,anchor_cluster_gap=3,
    tube_radius_range=[1.25,3.5],
    causal_rule='Erase target plus 4px before ALL curve-estimation operations. Replacement grey is the median of outside pixels. Target ink is used only to measure residuals against independently predicted curves.',
    scope='Local quadratic parallel-family approximation. Hairpins, broken curves, and unsupported crossings abstain; never a standalone noise decision.')
NAMES=['available','neighbor_count','neighbor_rms','shape_deviation','curvature',
       'anchor_pairs','explained_ink_fraction','residual_ink_fraction','largest_residual_fraction',
       'residual_components','residual_holes','tube_target_fraction','ink_fraction','tube_radius']


def chains(mask):
    """Trace simple paths, stopping at branches; omit redundant diagonal edges."""
    coords={tuple(p) for p in np.argwhere(mask)}
    adjacent={}
    for y,x in coords:
        ns=[]
        for dy,dx in ((-1,0),(1,0),(0,-1),(0,1),(-1,-1),(-1,1),(1,-1),(1,1)):
            p=(y+dy,x+dx)
            if p not in coords:continue
            if dy and dx and ((y+dy,x) in coords or (y,x+dx) in coords):continue
            ns.append(p)
        adjacent[(y,x)]=sorted(ns)
    used=set();paths=[]
    def edge(a,b):return tuple(sorted((a,b)))
    for start in sorted(coords):
        if len(adjacent[start])==2:continue
        for second in adjacent[start]:
            if edge(start,second) in used:continue
            path=[start];previous,current=start,second
            while True:
                used.add(edge(previous,current));path.append(current)
                if len(adjacent[current])!=2:break
                nxt=next(p for p in adjacent[current] if p!=previous)
                if edge(current,nxt) in used:break
                previous,current=current,nxt
            if len(path)>=20:paths.append(np.array([(x,y) for y,x in path],dtype=float))
    # Closed loops do not provide through-going reference curves.
    return paths


def mask_box(shape,box,halo=0):
    h,w=shape;a,b,c,d=box
    mask=np.zeros(shape,bool)
    mask[max(0,math.floor(b)-halo):min(h,math.ceil(d)+halo),max(0,math.floor(a)-halo):min(w,math.ceil(c)+halo)]=True
    return mask


def levels(values):
    if not len(values):return []
    values=np.sort(values);groups=np.split(values,np.flatnonzero(np.diff(values)>3)+1)
    return [float(np.median(g)) for g in groups if len(g)>=2]


def infer_curves(image,box):
    """The predicted tube must be invariant to any changes inside the target."""
    gray=np.asarray(image.convert('L'),dtype=np.float32)/255
    target=mask_box(gray.shape,box);excluded=mask_box(gray.shape,box,4)
    tube=np.zeros_like(target);skeleton=np.zeros_like(target)
    info=dict(available=False,neighbor_count=0,neighbor_rms=0.,shape_deviation=0.,curvature=0.,anchor_pairs=0,tube_radius=0.)
    if not target.any() or (~excluded).sum()<64:return info,tube,skeleton
    outside=gray.copy();outside[excluded]=np.median(gray[~excluded])
    ink=(cv2.GaussianBlur(outside,(0,0),8)-outside)>18/255
    ink[excluded]=False;skeleton=thin(ink)
    paths=chains(skeleton)
    if len(paths)<2:return info,tube,skeleton
    gx=cv2.Sobel(outside,cv2.CV_32F,1,0,ksize=3);gy=cv2.Sobel(outside,cv2.CV_32F,0,1,ksize=3)
    distance=cv2.distanceTransform((~excluded).astype(np.uint8),cv2.DIST_L2,5)
    support=(distance>=6)&(distance<=48)
    xx=float(np.sum(gx[support]**2));yy=float(np.sum(gy[support]**2));xy=float(np.sum(gx[support]*gy[support]))
    theta=.5*math.atan2(2*xy,xx-yy)+math.pi/2
    tangent=np.array([math.cos(theta),math.sin(theta)]);normal=np.array([-tangent[1],tangent[0]])
    a,b,c,d=box;center=np.array([(a+c)/2,(b+d)/2])
    corners=np.array([[a,b],[a,d],[c,b],[c,d]])-center
    umin,umax=(corners@tangent).min(),(corners@tangent).max()
    vmin,vmax=(corners@normal).min(),(corners@normal).max()
    references=[]
    for path in paths:
        delta=path-center;u=delta@tangent;v=delta@normal
        if u.min()>umin-8 or u.max()<umax+8:continue
        use=(u>=umin-16)&(u<=umax+16)
        if use.sum()<20:continue
        u,v=u[use],v[use]
        if abs(np.median(v))>max(abs(vmin),abs(vmax))+48:continue
        coefficients=np.polyfit(u,v,2)
        rms=float(np.sqrt(np.mean((v-np.polyval(coefficients,u))**2)))
        if rms>2.5:continue
        references.append((coefficients,rms))
    info['neighbor_count']=len(references)
    if len(references)<2:return info,tube,skeleton
    coeffs=np.array([r[0] for r in references]);curve=np.median(coeffs,axis=0);curve[2]=0
    samples=np.array([umin,0,umax])
    shapes=np.stack([np.polyval(c,samples)-c[2] for c in coeffs])
    deviation=float(np.max(np.abs(shapes-np.median(shapes,axis=0))))
    info.update(neighbor_rms=float(np.median([r[1] for r in references])),shape_deviation=deviation,curvature=float(curve[0]))
    if deviation>6:return info,tube,skeleton
    sy,sx=np.nonzero(skeleton);delta=np.column_stack([sx,sy])-center
    u=delta@tangent;v=delta@normal;intercepts=v-np.polyval(curve,u)
    normal_band=(v>=vmin-5)&(v<=vmax+5)
    left=levels(intercepts[normal_band&(u>=umin-15)&(u<=umin-3)])
    right=levels(intercepts[normal_band&(u>=umax+3)&(u<=umax+15)])
    pairs=[];used=set()
    for l in left:
        choices=[(abs(l-r),j,r) for j,r in enumerate(right) if j not in used and abs(l-r)<=3]
        if choices:
            _,j,r=min(choices);pairs.append((l+r)/2);used.add(j)
    info['anchor_pairs']=len(pairs)
    if not pairs:return info,tube,skeleton
    width=cv2.distanceTransform(ink.astype(np.uint8),cv2.DIST_L2,5)
    radius=float(np.clip(np.median(width[skeleton])+0.5,1.25,3.5));info['tube_radius']=radius
    yy,xx=np.indices(gray.shape);delta=np.stack([xx-center[0],yy-center[1]],axis=-1)
    uu=delta@tangent;vv=delta@normal
    # Approximate normal distance to a shallow quadratic; uncertainty remains a feature.
    norm=np.sqrt(1+(2*curve[0]*uu+curve[1])**2)
    for intercept in pairs:tube|=(np.abs(vv-np.polyval(curve,uu)-intercept)/norm<=radius)
    tube&=target
    info['available']=True
    return info,tube,skeleton


def extract(image,box,diagnostic=False):
    info,tube,skeleton=infer_curves(image,box)
    gray=np.asarray(image.convert('L'),dtype=np.float32)/255
    target=mask_box(gray.shape,box)
    ink=((cv2.GaussianBlur(gray,(0,0),8)-gray)>18/255)&target
    residual=ink&~tube;total=int(ink.sum());count,labels,stats,_=cv2.connectedComponentsWithStats(residual.astype(np.uint8),8)
    areas=stats[1:,cv2.CC_STAT_AREA]
    contours,hierarchy=cv2.findContours(residual.astype(np.uint8),cv2.RETR_CCOMP,cv2.CHAIN_APPROX_SIMPLE)
    holes=0 if hierarchy is None else sum(1 for h in hierarchy[0] if h[3]>=0)
    info.update(explained_ink_fraction=float((ink&tube).sum()/max(1,total)),
        residual_ink_fraction=float(residual.sum()/max(1,total)),largest_residual_fraction=float(max(areas,default=0)/max(1,total)),
        residual_components=int(sum(areas>=3)),residual_holes=holes,
        tube_target_fraction=float(tube.sum()/max(1,target.sum())),ink_fraction=float(total/max(1,target.sum())))
    vector=np.array([float(info[name]) for name in NAMES],dtype=np.float32)
    if diagnostic:return vector,info,dict(tube=tube,ink=ink,residual=residual,skeleton=skeleton)
    return vector,info
