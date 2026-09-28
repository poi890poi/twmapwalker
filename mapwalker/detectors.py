"""Experimental, inspectable proposal generators. Reviews are never runtime inputs."""
import hashlib
import importlib.metadata
import json
import time
from pathlib import Path

import cv2
import numpy as np

from .sources import SNAPSHOT
from .trails import trail_proposals, protect_trail_dashes

PAD = 64
CONFIG = dict(pad=PAD, ink_threshold=135, min_area=10, max_area=1600,
              min_side=4, max_side=72, repeat_similarity=0.87, repeat_count=4,
              urban_window=41, urban_density=0.035, urban_overlap=0.15, displacement_guard_px=16,
              text_score=0.45, upscale=2, text_angles=[-45,45])


def specs():
    folder = Path(__file__).parent
    code = {p.name:hashlib.sha256(p.read_bytes()).hexdigest() for p in
            [folder/'detectors.py', folder/'angled.py', folder/'junctions.py', folder/'trails.py', folder/'trail_paths.py', folder/'geo.py', folder/'sources.py', folder/'worker.py']}
    packages = {name:importlib.metadata.version(name) for name in
                ['numpy','pillow','opencv-python','rapidocr-onnxruntime','onnxruntime']}
    import rapidocr_onnxruntime
    models = {p.name:hashlib.sha256(p.read_bytes()).hexdigest() for p in
              (Path(rapidocr_onnxruntime.__file__).parent/'models').glob('*.onnx')}
    if not models:
        raise RuntimeError('OCR model files missing; refusing an unidentified model run')
    result = []
    for name in ('text', 'symbols', 'junctions', 'trails', 'angled-text'):
        spec = dict(name=name, version='0.2.0-experimental' if name=='trails' else '0.1.0-experimental', config=CONFIG, code=code,
                    packages=packages, models=models if name in ('text','angled-text') else {}, snapshot=SNAPSHOT)
        spec['fingerprint'] = hashlib.sha256(json.dumps(spec,sort_keys=True).encode()).hexdigest()
        result.append(spec)
    from .regions import region_spec
    extra=region_spec(CONFIG,code,SNAPSHOT)
    if extra:
        result.append(extra)
    return result


def developed_mask(image, config=CONFIG):
    """EMAP lavender building fill + neighborhood density; not cadastral truth."""
    rgb = np.asarray(image.convert('RGB')).astype(np.int16)
    r,g,b = rgb[:,:,0],rgb[:,:,1],rgb[:,:,2]
    building = ((r>=215)&(r<=244)&(g>=209)&(g<=238)&(b>=215)&(b<=246)&
                (r-g>=3)&(b-g>=3)&(np.abs(r-b)<=6)).astype(np.uint8)
    # JPEG ringing must not convert isolated tinted pixels into developed areas.
    count, labels, stats, _ = cv2.connectedComponentsWithStats(building,8)
    clean = np.zeros_like(building)
    for i in range(1,count):
        if stats[i,cv2.CC_STAT_AREA]>=6:
            clean[labels==i] = 1
    density = cv2.boxFilter(clean.astype(np.float32),-1,(config['urban_window'],)*2,
                            normalize=True,borderType=cv2.BORDER_CONSTANT)
    return density >= config['urban_density']


def symbol_proposals(image, config=CONFIG):
    gray = cv2.cvtColor(np.asarray(image),cv2.COLOR_RGB2GRAY)
    ink = (gray < config['ink_threshold']).astype(np.uint8)
    count, labels, stats, _ = cv2.connectedComponentsWithStats(ink,8)
    candidates = []
    for i in range(1,count):
        x,y,w,h,area = map(int,stats[i])
        fill = area/(w*h)
        if not (config['min_area']<=area<=config['max_area'] and
                config['min_side']<=min(w,h) and max(w,h)<=config['max_side'] and
                max(w,h)/min(w,h)<=3 and 0.08<=fill<=0.85):
            continue
        patch = (labels[y:y+h,x:x+w]==i).astype(np.uint8)
        # Keep aspect ratio and whitespace when comparing symbols.
        side = max(w,h)
        square = np.zeros((side,side),np.uint8)
        square[(side-h)//2:(side-h)//2+h,(side-w)//2:(side-w)//2+w] = patch
        signature = cv2.resize(square,(20,20),interpolation=cv2.INTER_AREA).flatten().astype(bool)
        candidates.append(dict(kind='symbol',text='',box=[x,y,x+w,y+h],score=0.35,
                               signature=signature, details=dict(area=area,fill=fill)))
    for i, item in enumerate(candidates):
        peers = 0
        a = item['signature']
        ax,ay,bx,by = item['box']
        for other in candidates:
            cx,cy,dx,dy = other['box']
            ratio = ((bx-ax)*(by-ay))/((dx-cx)*(dy-cy))
            if not 0.65<=ratio<=1.54:
                continue
            b = other['signature']
            similarity = np.count_nonzero(a&b)/max(1,np.count_nonzero(a|b))
            if similarity>=config['repeat_similarity']:
                peers += 1
        item['details']['similar_components'] = peers
        item['repeating'] = peers >= config['repeat_count']
    for item in candidates:
        del item['signature']
    return protect_trail_dashes(candidates,trail_proposals(image,config),ink.shape)


class TextDetector:
    def __init__(self):
        from rapidocr_onnxruntime import RapidOCR
        self.engine = RapidOCR(text_score=CONFIG['text_score'], intra_op_num_threads=2, inter_op_num_threads=1)

    def __call__(self, image, config=CONFIG):
        scale = config['upscale']
        rgb = np.asarray(image.resize((image.width*scale,image.height*scale)))
        output, _ = self.engine(cv2.cvtColor(rgb,cv2.COLOR_RGB2BGR))
        result = []
        for points, text, score in output or []:
            pts = np.asarray(points)/scale
            readings=[dict(direction='as-recognized',text=text)]
            width=float(pts[:,0].max()-pts[:,0].min());height=float(pts[:,1].max()-pts[:,1].min())
            if len(text)>1 and all('\u3400'<=c<='\u9fff' for c in text) and width>height*1.2:
                readings.append(dict(direction='possible-right-to-left',text=text[::-1]))
            result.append(dict(kind='text',text=text,score=float(score),
                               box=[float(pts[:,0].min()),float(pts[:,1].min()),
                                    float(pts[:,0].max()),float(pts[:,1].max())],
                               repeating=False,details={'recognition':'Chinese PP-OCR; historical Japanese unvalidated',
                                                        'angle_degrees_ccw':0,'polygon':pts.tolist(),
                                                        'reading_candidates':readings}))
        return result


def filter_proposals(proposals, mask, config=CONFIG, repetition=True, urban=True):
    """Retain every rejection; only centers in the owner tile are published."""
    output = []
    pad = config['pad']
    # Protect map-to-map boundary uncertainty. This is a review margin, not a
    # measured georeferencing error bound; never snap historical marks to NLSC.
    radius = config['displacement_guard_px']
    interior = cv2.erode(mask.astype(np.uint8),np.ones((2*radius+1,2*radius+1),np.uint8),
                         borderType=cv2.BORDER_CONSTANT,borderValue=0).astype(bool)
    for proposal in proposals:
        x0,y0,x1,y1 = proposal['box']
        cx,cy = (x0+x1)/2,(y0+y1)/2
        if not (pad<=cx<pad+256 and pad<=cy<pad+256):
            continue
        item = {**proposal,'details':dict(proposal.get('details',{}))}
        patch = mask[max(0,int(y0)):min(mask.shape[0],int(np.ceil(y1))),
                     max(0,int(x0)):min(mask.shape[1],int(np.ceil(x1)))]
        overlap = float(patch.mean()) if patch.size else 0
        item['details']['developed_overlap'] = overlap
        core = interior[max(0,int(y0)):min(mask.shape[0],int(np.ceil(y1))),
                        max(0,int(x0)):min(mask.shape[1],int(np.ceil(x1)))]
        core_overlap = float(core.mean()) if core.size else 0
        item['details']['developed_interior_overlap'] = core_overlap
        item['details']['position_quality'] = 'Historical map coordinate; local displacement unmeasured'
        item['details']['boundary_review'] = overlap>=config['urban_overlap'] and core_overlap<config['urban_overlap']
        reasons = []
        if repetition and item.get('repeating') and not item['details'].get('trail_context'):
            reasons.append('repeating-pattern')
        if urban and core_overlap>=config['urban_overlap']:
            reasons.append('developed-area')
        item['disposition'] = 'excluded' if reasons else 'candidate'
        item['reason'] = ', '.join(reasons) or None
        item['box'] = [float(x0-pad),float(y0-pad),float(x1-pad),float(y1-pad)]
        output.append(item)
    return output
