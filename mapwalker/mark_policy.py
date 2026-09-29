"""Synthetic-map CRAFT policy. Pixel detections only; never readings or reviews."""
from .region_model import iou

PROFILE = 'synthetic-map-v1'
PEAK = .95


def mark_regions(proposals, all_proposals):
    """Retain one-orientation discoveries; expose consistency separately."""
    output=[]
    for p in proposals:
        if p['score'] < PEAK:
            continue
        support=[q for q in all_proposals if q['score']>=PEAK and iou(p['box'],q['box'])>=.25]
        angles=sorted({q['details']['angle_degrees_ccw'] for q in support})
        scales=sorted({q['details']['scale'] for q in support})
        output.append({**p, 'score':min(1.,p['score']), 'details':{
            **p['details'], 'profile':PROFILE, 'method':'Synthetic-map CRAFT mark region',
            'raw_peak':p['score'], 'support_angles':angles, 'support_scales':scales,
            'interpretation':'Unread mark: may be text or a map symbol; inspect the source image',
            'score_meaning':'Synthetic-trained region activation, clipped to [0,1]; not POI probability',
        }})
    return output
