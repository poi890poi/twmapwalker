"""Manual annotation transactions and explainable OSM candidate ranking."""
import json
import time
import uuid

from .names import canonical_reading, match_name
from .writing_direction import infer_direction


def selected_rows(db,poi_id,members):
    members=set(members)|{poi_id}
    if len(members)>100:raise ValueError('A group can contain at most 100 fragments.')
    rows=[dict(r) for r in db.execute('''SELECT p.id,p.text,p.box,p.details,t.source,t.x,t.y,t.z
        FROM pois p JOIN jobs j ON j.id=p.job_id JOIN tiles t ON t.id=j.tile_id
        WHERE p.id IN ('''+','.join('?' for _ in members)+') ORDER BY p.id',sorted(members))]
    if len(rows)!=len(members):raise ValueError('A selected fragment no longer exists.')
    if len({r['source'] for r in rows})!=1:raise ValueError('Fragments must belong to the same historical map series.')
    return rows


def latest(db):
    return {r['poi_id']:json.loads(r['payload']) for r in db.execute(
        'SELECT a.poi_id,a.payload FROM annotations a WHERE a.id=(SELECT MAX(b.id) FROM annotations b WHERE b.poi_id=a.poi_id)')}


def group_members(db,poi_id,annotation):
    group=annotation.get('group_id')
    ids=[pid for pid,a in latest(db).items() if group and a.get('group_id')==group] if group else [poi_id]
    return [dict(r) for r in db.execute('''SELECT p.id,p.text,p.kind,p.lon,p.lat,p.box,t.x,t.y,t.z,
        (SELECT value FROM readings WHERE poi_id=p.id ORDER BY id DESC LIMIT 1) reading
        FROM pois p JOIN jobs j ON j.id=p.job_id JOIN tiles t ON t.id=j.tile_id
        WHERE p.id IN ('''+','.join('?' for _ in ids)+') ORDER BY p.id',ids)]


def save(db,poi_id,incoming):
    payload=dict(incoming)
    exact=payload.pop('member_ids',None)
    added=payload.pop('fragment_ids',[])
    sync=payload.pop('sync_reading',False)
    if exact is not None and added:raise ValueError('Use a complete member selection or added fragments, not both.')
    reading=canonical_reading(payload.get('ground_truth',''))
    if sync and len(reading)>80:raise ValueError('The map label can contain at most 80 characters.')
    db.execute('BEGIN IMMEDIATE')
    previous=latest(db)
    old_group=previous.get(poi_id,{}).get('group_id')
    old_members={pid for pid,a in previous.items() if old_group and a.get('group_id')==old_group}|{poi_id}
    if exact is not None:
        members=set(exact)|{poi_id}
    else:
        members=set(added)|old_members
        # Legacy append mode keeps existing groups intact.
        groups={previous.get(pid,{}).get('group_id') for pid in members}-{None}
        members|={pid for pid,a in previous.items() if a.get('group_id') in groups}
    rows=selected_rows(db,poi_id,members)
    if payload.get('map_direction')=='auto':
        evidence=infer_direction(reading,rows)
        payload.update(map_direction=evidence['direction'],direction_source='automatic',direction_evidence=evidence)
    else:payload['direction_source']='manual'
    group=(old_group or str(uuid.uuid4())) if len(members)>1 else None
    payload['group_id']=group
    if sync:payload['ground_truth']=reading
    now=time.time()
    for member in sorted(members|old_members):
        if member not in members:
            value={**previous.get(member,{}),'group_id':None}
        elif member==poi_id or sync:
            value=dict(payload)
        else:
            value={**previous.get(member,{}),'group_id':group}
        db.execute('INSERT INTO annotations(poi_id,payload,created) VALUES(?,?,?)',(member,json.dumps(value,ensure_ascii=False),now))
        if sync and member in members:
            status='confirmed' if payload['classification']=='poi' and reading and '?' not in reading else 'tentative'
            old=db.execute('SELECT value,status FROM readings WHERE poi_id=? ORDER BY id DESC LIMIT 1',(member,)).fetchone()
            if old is None or (old['value'],old['status'])!=(reading,status):
                db.execute('INSERT INTO readings(poi_id,value,status,origin,created) VALUES(?,?,?,?,?)',(member,reading,status,'manual',now))
            verdict={'poi':'confirmed','noise':'rejected','unclassified':'uncertain'}[payload['classification']]
            old=db.execute('SELECT verdict FROM reviews WHERE poi_id=? ORDER BY id DESC LIMIT 1',(member,)).fetchone()
            if old is None or old['verdict']!=verdict:
                db.execute('INSERT INTO reviews(poi_id,verdict,note,created) VALUES(?,?,?,?)',(member,verdict,payload.get('note',''),now))
    return payload


def rank_osm(features,text):
    """Rank within the fetched radius; scores are text similarity, not confidence."""
    text=canonical_reading(text)
    enough=sum(c.isalnum() for c in text)>=2
    ranked=[]
    for feature in features:
        properties=feature['properties']
        names={properties.get('name','')}
        for key,value in properties.get('tags',{}).items():
            if key.split(':')[0] in ('name','old_name','alt_name','official_name','short_name'):
                names.update(value.split(';'))
        matches=[(match_name(text,name),name) for name in sorted(names) if name] if enough else []
        matches=[(m,name) for m,name in matches if m]
        match,name=max(matches,key=lambda pair:pair[0]['score']) if matches else (None,'')
        explanation={'exact':'Name matches','contains':'Contains the entered text','unknown-character':'Matches known characters','similar-spelling':'Similar name'}.get(match['reason']) if match else 'Nearby geometry only'
        ranked.append({**feature,'properties':{**properties,'match_reason':explanation,'matched_name':name,'name_score':match['score'] if match else None}})
    ranked.sort(key=lambda f:(f['properties']['name_score'] is None,-(f['properties']['name_score'] or 0),f['properties']['distance_m'],f['properties']['osm_type'],f['properties']['osm_id']))
    return ranked[:12],enough
