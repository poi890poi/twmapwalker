"""Offline graph-continuation and neighboring-line pilot, never a POI filter."""
import json
import math
import time

import cv2
import numpy as np
from PIL import Image

from .contour_frequency_trial import ROOT, sha

OUT = ROOT / 'evidence/contour-topology/v2'
PARAMETERS = dict(
    input='Native context pixels and target box only; no labels, OCR, map elevation or POI type',
    threshold='Gaussian background sigma 8 minus grey > 18/255',
    skeleton='Zhang-Suen thinning; diagonal edges omitted when an orthogonal two-step connection exists',
    minimum_target_nodes=8, minimum_continuing_fraction=.90,
    minimum_component_length_box_diagonals=3, minimum_component_span_box_diagonals=1.5,
    maximum_internal_endpoints=0, maximum_internal_branch_fraction=.05,
    minimum_neighbor_long_components=3, neighbor_component_minimum_length=64,
    tensor_sigma=6, minimum_target_coherence=.70, minimum_neighbor_alignment=.80,
    neighbor_band_pixels=[8,32],
    acceptance='At least one contour hit and zero protected/uncertain hits to seek a fresh holdout. No threshold tuning.',
    scope='Tooling only. Labels score predictions after extraction. No DB or application writes; stop rejected methods.')


def thin(mask):
    a = np.pad(mask.astype(np.uint8), 1)
    while True:
        removed = 0
        for phase in (0, 1):
            p = [a[:-2,1:-1], a[:-2,2:], a[1:-1,2:], a[2:,2:],
                 a[2:,1:-1], a[2:,:-2], a[1:-1,:-2], a[:-2,:-2]]
            n = sum(p)
            transitions = sum(((p[i] == 0) & (p[(i+1)%8] == 1)).astype(np.uint8) for i in range(8))
            if phase == 0:
                clear = (p[0]*p[2]*p[4] == 0) & (p[2]*p[4]*p[6] == 0)
            else:
                clear = (p[0]*p[2]*p[6] == 0) & (p[0]*p[4]*p[6] == 0)
            center = a[1:-1,1:-1]
            delete = (center == 1) & (n >= 2) & (n <= 6) & (transitions == 1) & clear
            removed += int(delete.sum())
            center[delete] = 0
        if not removed:
            return a[1:-1,1:-1].astype(bool)


def graph_degree(skel):
    """Avoid artificial triangles along raster bends without breaking diagonals."""
    a = np.pad(skel,1)
    n,e,s,w = a[:-2,1:-1],a[1:-1,2:],a[2:,1:-1],a[1:-1,:-2]
    ne,se,sw,nw = a[:-2,2:],a[2:,2:],a[2:,:-2],a[:-2,:-2]
    return sum(v.astype(np.uint8) for v in (n,e,s,w,
        ne & ~n & ~e,se & ~s & ~e,sw & ~s & ~w,nw & ~n & ~w))


def features(image, box):
    a = np.asarray(image.convert('L'), dtype=np.float32) / 255
    ink = (cv2.GaussianBlur(a, (0,0), 8) - a) > 18/255
    skel = thin(ink)
    h,w = a.shape
    left,top,right,bottom = box
    x0,y0 = max(0,math.floor(left)),max(0,math.floor(top))
    x1,y1 = min(w,math.ceil(right)),min(h,math.ceil(bottom))
    target = np.zeros_like(skel); target[y0:y1,x0:x1] = True
    nodes = skel & target
    n = int(nodes.sum())
    if n < PARAMETERS['minimum_target_nodes']:
        return dict(available=False,reason='too few target skeleton nodes',target_nodes=n)
    # Crossings / branch clusters abstain; no forced reconnection of broken ink.
    degree = graph_degree(skel)
    inside = np.zeros_like(skel)
    inside[min(y0+2,y1):max(y0+2,y1-2),min(x0+2,x1):max(x0+2,x1-2)] = True
    internal = nodes & inside
    ends = int(((degree <= 1) & internal).sum())
    branches = float(((degree >= 3) & internal).sum() / max(1,internal.sum()))
    count, labels, stats, _ = cv2.connectedComponentsWithStats(skel.astype(np.uint8), 8)
    diagonal = max(1,math.hypot(right-left,bottom-top))
    ids = [int(i) for i in np.unique(labels[nodes]) if i]
    long_ids = [i for i in ids if stats[i,cv2.CC_STAT_AREA] >= 3*diagonal
                and math.hypot(stats[i,cv2.CC_STAT_WIDTH],stats[i,cv2.CC_STAT_HEIGHT]) >= 1.5*diagonal]
    continuing = float(np.isin(labels[nodes],long_ids).mean())
    distance = cv2.distanceTransform((~target).astype(np.uint8),cv2.DIST_L2,5)
    band = skel & (distance >= 8) & (distance <= 32)
    neighbors = [int(i) for i in np.unique(labels[band]) if i and i not in ids
                 and stats[i,cv2.CC_STAT_AREA] >= 64]
    # Local orientation lets curved contours agree locally, unlike one global axis.
    gx = cv2.Sobel(a,cv2.CV_32F,1,0,ksize=3)
    gy = cv2.Sobel(a,cv2.CV_32F,0,1,ksize=3)
    xx = cv2.GaussianBlur(gx*gx,(0,0),6)
    yy = cv2.GaussianBlur(gy*gy,(0,0),6)
    xy = cv2.GaussianBlur(gx*gy,(0,0),6)
    coherence = np.hypot(xx-yy,2*xy)/(xx+yy+1e-9)
    angle = np.arctan2(2*xy,xx-yy)
    direction = np.mean(np.exp(1j*angle[nodes]))
    neighbor_nodes = band & np.isin(labels,neighbors)
    alignment = float(np.mean((1+np.cos(angle[neighbor_nodes]-np.angle(direction)))/2)) if neighbor_nodes.any() else 0
    coh = float(np.median(coherence[nodes]))
    graph = continuing >= .90 and ends == 0 and branches <= .05 and len(neighbors) >= 3
    parallel = coh >= .70 and alignment >= .80
    return dict(available=True,target_nodes=n,continuing_fraction=continuing,
                internal_endpoints=ends,internal_branch_fraction=branches,
                neighboring_long_components=len(neighbors),target_coherence=coh,
                neighbor_alignment=alignment,graph=graph,parallel=parallel,
                topology_and_parallel=graph and parallel)


def main():
    OUT.mkdir(exist_ok=False)
    (OUT/'parameters.json').write_text(json.dumps(PARAMETERS,indent=2)+'\n',encoding='utf8')
    rows=json.loads((ROOT/'evidence/contour-frequency/samples.json').read_text(encoding='utf8'))
    predictions=[]
    for row in rows:
        path=ROOT/row['context']; assert sha(path)==row['context_sha256']
        with Image.open(path) as im: image=im.convert('RGB')
        start=time.perf_counter(); f=features(image,row['context_box']); elapsed=(time.perf_counter()-start)*1000
        predictions.append(dict(id=row['id'],origin=row['origin'],features=f,feature_ms=elapsed))
    # Save automatic-only telemetry before joining evaluation labels.
    (OUT/'predictions.json').write_text(json.dumps(predictions,indent=2)+'\n',encoding='utf8')
    summary={}
    for method in ('parallel','graph','topology_and_parallel'):
        hits=[row for row,pred in zip(rows,predictions) if pred['features'].get(method,False)]
        neg=sum(row['negative'] for row in hits)
        false=[dict(id=row['id'],origin=row['origin'],label=row['label']) for row in hits if not row['negative']]
        summary[method]=dict(contour_hits=neg,contour_total=138,protected_or_uncertain_hits=len(false),
                             protected_or_uncertain_total=112,false_rejections=false,
                             decision='reject' if false or not neg else 'retain; needs genuinely fresh holdout')
    (OUT/'summary.json').write_text(json.dumps(summary,indent=2)+'\n',encoding='utf8')
    (OUT/'lock.json').write_text(json.dumps(dict(code_sha256=sha(ROOT/'tools/contour_topology_trial.py'),
        samples_sha256=sha(ROOT/'evidence/contour-frequency/samples.json'),opencv=cv2.__version__,numpy=np.__version__),indent=2)+'\n',encoding='utf8')
    print(json.dumps(summary,indent=2))


if __name__=='__main__':main()
