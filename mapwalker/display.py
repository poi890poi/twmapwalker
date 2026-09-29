"""Automatic, read-only display priorities. These are not POI probabilities."""
import heapq
import json
import math
import re

from .geo import world, lonlat
from .names import reading_options

VERSION='display-2'
CELL_PIXELS=128
LEVELS={'top':(.74,1),'reduced':(.50,5),'adaptive':(.38,2)}


def context_bounds(bbox,zoom):
    w,s,e,n=bbox
    x0,y0=world(w,n,zoom);x1,y1=world(e,s,zoom)
    step=CELL_PIXELS/256
    west,north=lonlat(math.floor(x0/step)*step,math.floor(y0/step)*step,zoom)
    east,south=lonlat(math.ceil(x1/step)*step,math.ceil(y1/step)*step,zoom)
    return max(118,west),max(21.5,south),min(123,east),min(26.5,north)


def priority(row):
    """Use raw automatic features only, never manual readings or reviews."""
    p=dict(row);d=json.loads(p['details']) if isinstance(p['details'],str) else p['details']
    score=max(0,min(1,float(p['score'])))
    box=json.loads(p['box']) if isinstance(p['box'],str) else p['box']
    width,height=abs(box[2]-box[0]),abs(box[3]-box[1])
    if p['kind']=='text':
        if d.get('profile')=='synthetic-map-v1':
            # Rotation agreement is automatic support, not a recognized name.
            angles=len(set(d.get('support_angles',[])))
            if min(width,height)<12 or max(width,height)>240:return .50
            return .78+.01*min(angles,6) if angles>=2 else .68
        raw=next(iter(reading_options(dict(text=p['text'],details=d))), '')
        if re.search(r'[\u3040-\u30ff\u3400-\u9fff]',raw):return .72+.25*score
        if raw and re.fullmatch(r'[\d\s.,?°+-]+',raw):return .18+.10*score
        if raw:return .30+.20*score
        # Retain unread, rotated character regions without requiring OCR success.
        if min(width,height)>=12 and max(width,height)<=240:return .60+.25*score
        return .30+.20*score
    if p['kind']=='trail':
        return min(.94,.34+.06*min(d.get('dash_count',0),10))
    if 'junction_count' in d:return .30+.05*min(d['junction_count'],6)
    fill=d.get('fill',0);similar=d.get('similar_components',99)
    compact=min(width,height)>=8 and max(width,height)<=96 and max(width,height)/max(1,min(width,height))<=3
    if not compact or d.get('area',0)<45 or not .15<=fill<=.70 or similar>3:return .25
    return .58+.08*(.18<=fill<=.65)+.08*(similar==1)+.04*bool(d.get('trail_context'))


def intersects(row,bbox):
    w,s,e,n=bbox
    return (row['east'] if row['east'] is not None else row['lon'])>=w and (row['west'] if row['west'] is not None else row['lon'])<=e and (row['north'] if row['north'] is not None else row['lat'])>=s and (row['south'] if row['south'] is not None else row['lat'])<=n


def choose(rows,bbox,zoom,level):
    floor,budget=LEVELS[level];cells={};visible={};before=0
    for row in rows:
        in_view=intersects(row,bbox)
        if in_view:before+=1
        rank=round(priority(row),6)
        if rank<floor:continue
        x,y=world(row['lon'],row['lat'],zoom)
        key=(row['source'],math.floor(x*256/CELL_PIXELS),math.floor(y*256/CELL_PIXELS))
        entry=(rank,-row['id'],row['id'],in_view)
        heap=cells.setdefault(key,[])
        if len(heap)<budget:heapq.heappush(heap,entry)
        elif entry>heap[0]:heapq.heapreplace(heap,entry)
    for heap in cells.values():
        for rank,_,pid,in_view in heap:
            if in_view:visible[pid]=rank
    return visible,dict(level=level,version=VERSION,available=before,shown=len(visible),
                        hidden=before-len(visible),cell_pixels=CELL_PIXELS,per_cell=budget,
                        score_meaning='Automatic display priority, not verified POI quality')
