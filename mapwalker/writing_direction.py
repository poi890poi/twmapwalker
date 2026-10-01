"""Infer map writing direction from a supplied reading and spatial OCR evidence.

Only exact, uniquely identifiable glyphs vote. This does not recognize new glyphs
or use place-name suggestions as evidence. Inference is reviewable, not truth.
"""
from collections import Counter, defaultdict
import json
import math
import unicodedata

from .names import search_key


def decoded(value, default):
    if isinstance(value,str):
        try:return json.loads(value)
        except ValueError:return default
    return value if value is not None else default


def glyph_positions(row):
    text=search_key(row.get('text') or '')
    box=decoded(row.get('box'),[])
    if not text or len(box)!=4:return []
    try:
        x0,y0,x1,y1=map(float,box)
        tile_x,tile_y,z=(float(row[k]) for k in ('x','y','z'))
    except (KeyError,TypeError,ValueError):return []
    if not all(map(math.isfinite,(x0,y0,x1,y1,tile_x,tile_y,z))) or not 0<=z<=24:return []
    width,height=x1-x0,y1-y0
    if min(width,height)<=0:return []
    center=((x0+x1)/2,(y0+y1)/2)
    dx,dy=width,0
    if len(text)>1:
        # Bidi OCR strings are commonly returned in logical order, so string
        # reversal alone says nothing about their physical glyph placement.
        if any(unicodedata.bidirectional(c) in ('R','AL','AN') for c in text):return []
        details=decoded(row.get('details'),{})
        polygon=details.get('polygon',[])
        if len(polygon)==4:
            # Polygon order survives the detector's inverse rotation transform.
            try:
                dx=(polygon[1][0]+polygon[2][0]-polygon[0][0]-polygon[3][0])/2
                dy=(polygon[1][1]+polygon[2][1]-polygon[0][1]-polygon[3][1])/2
                across=math.hypot(dx,dy)
                down=math.hypot(polygon[3][0]-polygon[0][0],polygon[3][1]-polygon[0][1])
            except (TypeError,IndexError):return []
            if across<=down*1.2:
                # Tall unrotated OCR crops have vertical layout; internal OCR
                # rotation may reverse order, but the public result is vertical.
                if height>width*1.5:dx,dy=0,height
                else:return []
        else:
            angle=details.get('angle_degrees_ccw',0)
            if not isinstance(angle,(int,float)) or not math.isfinite(angle):return []
            if width>height*1.5 and abs(math.sin(math.radians(angle)))<.1:
                dx=width if math.cos(math.radians(angle))>0 else -width
            elif height>width*1.5:dx,dy=0,height
            else:return []
    scale=256*2**z
    size=min(width,height,math.hypot(dx,dy)/len(text))/scale
    counts=Counter(text)
    return [dict(glyph=c,x=(tile_x*256+center[0]+((i+.5)/len(text)-.5)*dx)/scale,
                 y=(tile_y*256+center[1]+((i+.5)/len(text)-.5)*dy)/scale,
                 size=size,poi_id=row['id'])
            for i,c in enumerate(text) if c.isalnum() and counts[c]==1]


def infer_direction(label,rows):
    label=search_key(label)
    unique={c:i for i,c in enumerate(label) if c.isalnum() and label.count(c)==1}
    observations=defaultdict(list)
    for row in rows:
        for glyph in glyph_positions(row):
            if glyph['glyph'] in unique:observations[glyph['glyph']].append(glyph)
    anchors=[]
    for glyph,points in observations.items():
        first=points[0]
        # Duplicate detections of one position count once. Multiple plausible
        # positions for the same character cannot establish its order.
        if any(math.hypot(p['x']-first['x'],p['y']-first['y'])>max(p['size'],first['size'])*.5 for p in points[1:]):continue
        anchors.append({**first,'index':unique[glyph]})
    anchors.sort(key=lambda a:a['index'])
    votes=set();support=set()
    for i,a in enumerate(anchors):
        for b in anchors[i+1:]:
            dx,dy=b['x']-a['x'],b['y']-a['y']
            if math.hypot(dx,dy)<max(a['size'],b['size'])*.5:continue
            if abs(dx)>abs(dy)*1.5:direction='ltr' if dx>0 else 'rtl'
            elif abs(dy)>abs(dx)*1.5:direction='vertical'
            else:continue
            votes.add(direction);support.update((a['glyph'],b['glyph']))
    direction=next(iter(votes)) if len(votes)==1 else 'unknown'
    reason=('glyph-order' if direction!='unknown' else 'conflicting-glyph-order' if len(votes)>1
            else 'insufficient-glyph-evidence')
    return dict(method='glyph-order-v1',direction=direction,reason=reason,matched_glyphs=[a['glyph'] for a in anchors if a['glyph'] in support],
                poi_ids=sorted({a['poi_id'] for a in anchors if a['glyph'] in support}))
