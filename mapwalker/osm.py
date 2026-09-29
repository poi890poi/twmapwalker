"""Versioned OSM supporting context, independent of historical-map detection."""
import hashlib
import json
import math
import sqlite3
import threading
import time
import urllib.parse
import urllib.request
from contextlib import contextmanager
from pathlib import Path

ENDPOINT='https://overpass-api.de/api/interpreter'
VERSION='osm-context-1'
TTL=30*86400
MAX_BYTES=8*1024*1024
SELECTORS=[
    'nwr["historic"]', 'nwr["heritage"]',
    'way["highway"~"^(path|footway|track|steps|bridleway)$"]',
    'relation["route"="hiking"]', 'nwr["natural"="hot_spring"]',
    'nwr["natural"~"^(peak|saddle|waterfall|cave_entrance)$"]',
    'nwr["tourism"~"^(viewpoint|alpine_hut|wilderness_hut)$"]',
    'nwr["amenity"~"^(school|place_of_worship)$"]',
    'nwr["man_made"~"^(survey_point|watermill)$"]',
    'nwr["place"~"^(hamlet|village|locality)$"]',
    'nwr["waterway"~"^(stream|river|waterfall)$"]',
]


def query_for(bbox):
    w,s,e,n=bbox;area=f'{s:.5f},{w:.5f},{n:.5f},{e:.5f}'
    return '[out:json][timeout:30][maxsize:67108864];('+''.join(f'{selector}({area});' for selector in SELECTORS)+f');out body geom({area});'


def cell(lon,lat):
    x,y=math.floor(lon*50),math.floor(lat*50)
    bbox=[max(118,x/50-.015),max(21.5,y/50-.015),min(123,(x+1)/50+.015),min(26.5,(y+1)/50+.015)]
    query=query_for(bbox)
    key=hashlib.sha256((VERSION+query).encode()).hexdigest()
    return key,bbox,query


def coordinate(raw):
    if not isinstance(raw,dict):return None
    lon,lat=raw.get('lon'),raw.get('lat')
    if isinstance(lon,(int,float)) and isinstance(lat,(int,float)) and math.isfinite(lon+lat) and -180<=lon<=180 and -90<=lat<=90:
        return [lon,lat]


def lines(raw):
    """Never bridge a missing/cropped geometry section."""
    output=[];line=[]
    for value in raw:
        point=coordinate(value)
        if point is not None:line.append(point)
        else:
            if len(line)>1:output.append(line)
            line=[]
    if len(line)>1:output.append(line)
    return output


def normalize(payload):
    features=[];seen=set()
    if payload.get('remark'):raise ValueError('Overpass returned an incomplete response: '+str(payload['remark'])[:300])
    if not isinstance(payload.get('elements'),list):raise ValueError('Overpass response has no elements list')
    for element in payload['elements']:
        kind=element.get('type');oid=element.get('id');tags=element.get('tags') or {}
        if kind not in ('node','way','relation') or not isinstance(oid,int) or oid<=0 or not isinstance(tags,dict):continue
        if (kind,oid) in seen:continue
        seen.add((kind,oid))
        tags={str(k):str(v) for k,v in tags.items()}
        if kind=='node':
            point=coordinate(element)
            if point is None:continue
            geometry=dict(type='Point',coordinates=point)
        else:
            segments=lines(element.get('geometry',[])) if kind=='way' else [line for member in element.get('members',[]) for line in lines(member.get('geometry',[]))]
            if not segments:continue
            geometry=dict(type='MultiLineString',coordinates=segments)
        category=('trail' if tags.get('highway') in ('path','footway','track','steps','bridleway') or tags.get('route')=='hiking' else
                  'historic' if 'historic' in tags or 'heritage' in tags else 'waterway' if 'waterway' in tags else 'landmark')
        name=tags.get('name:zh') or tags.get('name') or tags.get('name:ja') or tags.get('old_name') or ''
        features.append(dict(type='Feature',geometry=geometry,properties=dict(osm_type=kind,osm_id=oid,
            url=f'https://www.openstreetmap.org/{kind}/{oid}',name=name,category=category,tags=tags)))
    return features


def distance_m(geometry,lon,lat):
    sx=111320*math.cos(math.radians(lat));sy=111320
    def xy(p):return (p[0]-lon)*sx,(p[1]-lat)*sy
    if geometry['type']=='Point':return math.hypot(*xy(geometry['coordinates']))
    best=math.inf
    for line in geometry['coordinates']:
        for a,b in zip(line,line[1:]):
            ax,ay=xy(a);bx,by=xy(b);dx,dy=bx-ax,by-ay
            ratio=max(0,min(1,-(ax*dx+ay*dy)/(dx*dx+dy*dy))) if dx or dy else 0
            best=min(best,math.hypot(ax+ratio*dx,ay+ratio*dy))
    return best


class OSMContext:
    def __init__(self,data):
        self.root=Path(data)/'osm';self.root.mkdir(parents=True,exist_ok=True)
        (self.root/'snapshots').mkdir(exist_ok=True)
        self.path=self.root/'context.sqlite3';self.stop=threading.Event()
        with self.connect() as db:
            db.execute('PRAGMA journal_mode=WAL')
            db.execute('''CREATE TABLE IF NOT EXISTS requests (
                key TEXT PRIMARY KEY,version TEXT NOT NULL,bbox TEXT NOT NULL,query TEXT NOT NULL,
                state TEXT NOT NULL,requested REAL NOT NULL,updated REAL,retry_at REAL NOT NULL DEFAULT 0,
                error TEXT,raw_path TEXT,digest TEXT)''')
            db.execute("UPDATE requests SET state='pending' WHERE state='running'")

    @contextmanager
    def connect(self):
        db=sqlite3.connect(self.path,timeout=10);db.row_factory=sqlite3.Row
        try:
            with db:yield db
        finally:db.close()

    def request(self,lon,lat):
        key,bbox,query=cell(lon,lat);now=time.time()
        with self.connect() as db:
            db.execute('''INSERT OR IGNORE INTO requests(key,version,bbox,query,state,requested)
                VALUES(?,?,?,?,'pending',?)''',(key,VERSION,json.dumps(bbox),query,now))
            row=db.execute('SELECT * FROM requests WHERE key=?',(key,)).fetchone()
            if (row['state']=='complete' and now-row['updated']>TTL) or (row['state']=='failed' and now>=row['retry_at']):
                db.execute("UPDATE requests SET state='pending',requested=? WHERE key=?",(now,key))
            return dict(db.execute('SELECT * FROM requests WHERE key=?',(key,)).fetchone())

    def context(self,lon,lat,radius=1000):
        row=self.request(lon,lat)
        result=dict(state=row['state'],version=VERSION,bbox=json.loads(row['bbox']),radius_m=radius,
            retrieved_at=row['updated'],stale=row['state']!='complete',error=row['error'],
            retry_at=row['retry_at'],features=[],total=0,endpoint=ENDPOINT,
            sha256=row['digest'],query=row['query'],license='ODbL 1.0',attribution='© OpenStreetMap contributors',
            note='Modern supporting context. Proximity is not confirmation of historical identity; coordinates may be displaced.')
        if row['raw_path']:
            raw=(self.root/row['raw_path']).read_bytes()
            if hashlib.sha256(raw).hexdigest()!=row['digest']:raise ValueError('OSM snapshot hash mismatch')
            nearby=[]
            for feature in normalize(json.loads(raw)):
                distance=distance_m(feature['geometry'],lon,lat)
                if distance<=radius:
                    feature['properties']['distance_m']=round(distance);nearby.append(feature)
            nearby.sort(key=lambda f:(f['properties']['distance_m'],f['properties']['osm_type'],f['properties']['osm_id']))
            result.update(features=nearby[:200],total=len(nearby),truncated=len(nearby)>200)
        return result

    @staticmethod
    def fetch(query):
        request=urllib.request.Request(ENDPOINT,data=urllib.parse.urlencode({'data':query}).encode(),
            headers={'User-Agent':'Mapwalker/0.1 (local Taiwan historical-map evidence viewer)',
                     'Content-Type':'application/x-www-form-urlencoded','Accept':'application/json'})
        with urllib.request.urlopen(request,timeout=40) as response:raw=response.read(MAX_BYTES+1)
        if len(raw)>MAX_BYTES:raise ValueError('OSM response exceeded 8 MB; context unavailable for this area')
        return raw

    def once(self,fetch=None):
        with self.connect() as db:
            db.execute('BEGIN IMMEDIATE')
            row=db.execute("SELECT * FROM requests WHERE state='pending' ORDER BY requested LIMIT 1").fetchone()
            if not row:return False
            db.execute("UPDATE requests SET state='running',error=NULL WHERE key=?",(row['key'],))
        try:
            raw=(fetch or self.fetch)(row['query']);normalize(json.loads(raw))
            digest=hashlib.sha256(raw).hexdigest();relative=f'snapshots/{digest}.json'
            target=self.root/relative
            if not target.exists():
                temporary=target.with_suffix('.tmp');temporary.write_bytes(raw);temporary.replace(target)
            with self.connect() as db:
                db.execute("UPDATE requests SET state='complete',updated=?,raw_path=?,digest=?,error=NULL,retry_at=0 WHERE key=?",
                           (time.time(),relative,digest,row['key']))
        except Exception as exc:
            with self.connect() as db:
                db.execute("UPDATE requests SET state='failed',error=?,retry_at=? WHERE key=?",(str(exc)[:500],time.time()+300,row['key']))
        return True

    def run(self):
        while not self.stop.is_set():self.stop.wait(5 if self.once() else 1)
