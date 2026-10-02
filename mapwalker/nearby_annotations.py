"""Saved-name editing assistance, deliberately separate from automatic inference."""
import json
import math

from .geo import pixel_lonlat
from .visibility import HIDDEN_SQL

RADIUS_M=500


def bounds(row):
    box=json.loads(row['box']) if isinstance(row['box'],str) else row['box']
    if len(box)!=4 or not all(math.isfinite(v) for v in box):raise ValueError('Invalid label box')
    west,north=pixel_lonlat(row['z'],row['x'],row['y'],box[0],box[1])
    east,south=pixel_lonlat(row['z'],row['x'],row['y'],box[2],box[3])
    return min(west,east),min(south,north),max(west,east),max(south,north)


def gap_m(a,b):
    dx=max(0,a[0]-b[2],b[0]-a[2])
    dy=max(0,a[1]-b[3],b[1]-a[3])
    latitude=(a[1]+a[3]+b[1]+b[3])/4
    return math.hypot(dx*111320*math.cos(math.radians(latitude)),dy*111320)


def suggest(db,poi_id):
    target=db.execute('''SELECT p.id,p.box,t.source,t.x,t.y,t.z FROM pois p
        JOIN jobs j ON p.job_id=j.id JOIN tiles t ON j.tile_id=t.id WHERE p.id=?''',(poi_id,)).fetchone()
    if target is None:raise LookupError('Candidate not found')
    rows=[dict(r) for r in db.execute(f'''SELECT p.id,p.box,t.source,t.x,t.y,t.z,a.payload,{HIDDEN_SQL} hidden
        FROM annotations a JOIN pois p ON p.id=a.poi_id JOIN jobs j ON p.job_id=j.id
        JOIN tiles t ON j.tile_id=t.id
        WHERE a.id=(SELECT MAX(b.id) FROM annotations b WHERE b.poi_id=a.poi_id)''')]
    for row in rows:row['annotation']=json.loads(row.pop('payload'))
    own=next((r['annotation'] for r in rows if r['id']==poi_id),{})
    group=own.get('group_id')
    members=[r for r in rows if group and r['annotation'].get('group_id')==group]
    excluded={poi_id}|{r['id'] for r in members}
    target_boxes=[bounds(target)]+[bounds(r) for r in members if r['id']!=poi_id]
    candidates=[]
    for row in rows:
        a=row['annotation'];name=a.get('ground_truth','').strip()
        if (row['id'] in excluded or row['hidden'] or a.get('classification')!='poi'
                or not any(c.isalnum() for c in name) or len(name)>80):continue
        distance=min(gap_m(b,bounds(row)) for b in target_boxes)
        if distance>RADIUS_M:continue
        candidates.append(dict(poi_id=row['id'],name=name,source=row['source'],classification=a['classification'],
            osm_type=a.get('osm_type',''),osm_id=a.get('osm_id'),osm_name=a.get('osm_name',''),
            distance_m=round(distance),same_map=row['source']==target['source'],
            relation='overlapping label boxes' if distance==0 else 'nearby label boxes',
            _group=a.get('group_id') or row['id'],_distance=distance))
    candidates.sort(key=lambda r:(r['_distance'],not r['same_map'],r['poi_id']))
    seen=set();names=set();result=[]
    for row in candidates:
        group=row.pop('_group');row.pop('_distance')
        identity=(row['name'],row['osm_type'] or '',row['osm_id'])
        if group in seen or identity in names:continue
        seen.add(group);names.add(identity);result.append(row)
        if len(result)==5:break
    return dict(radius_m=RADIUS_M,candidates=result,
                note='Saved annotations near the selected map boxes. Proximity does not establish the same place.')
