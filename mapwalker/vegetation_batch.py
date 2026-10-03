"""Versioned advisory backfill; manual decisions always own classification."""
import hashlib
import json
import time
import uuid
from functools import lru_cache
from pathlib import Path

from .vegetation_evidence import VegetationEvidence

AUTOMATIC = ('box', 'source', 'z', 'x', 'y', 'spec', 'manifest', 'kind')
JOINS = '''FROM pois p JOIN jobs j ON j.id=p.job_id JOIN tiles t ON t.id=j.tile_id
           JOIN algorithms a ON a.fingerprint=j.algorithm'''
ELIGIBLE = '''a.active=1 AND j.state='complete' AND p.disposition='candidate'
    AND p.kind IN ('text','symbol') AND t.z=16
    AND NOT EXISTS(SELECT 1 FROM annotations WHERE poi_id=p.id)
    AND NOT EXISTS(SELECT 1 FROM reviews WHERE poi_id=p.id)
    AND NOT EXISTS(SELECT 1 FROM readings WHERE poi_id=p.id)
    AND NOT EXISTS(SELECT 1 FROM poi_visibility WHERE poi_id=p.id)'''
FIELDS = 'p.id,p.kind,p.box,p.lon,p.lat,t.source,t.z,t.x,t.y,j.manifest,a.spec'


@lru_cache(maxsize=1)
def identity():
    import cv2
    import numpy
    import onnxruntime
    import rapidocr_onnxruntime
    root = Path(__file__).parent
    paths = [root/n for n in ('vegetation.py', 'vegetation_evidence.py', 'reading_suggestions.py', 'detectors.py')]
    paths += sorted((Path(rapidocr_onnxruntime.__file__).parent/'models').glob('*.onnx'))
    metadata = dict(policy='single-unreviewed-fragment-1', code_models={p.name:hashlib.sha256(p.read_bytes()).hexdigest() for p in paths},
                    runtime=dict(opencv=cv2.__version__, numpy=numpy.__version__, onnxruntime=onnxruntime.__version__))
    return hashlib.sha256(json.dumps(metadata,sort_keys=True).encode()).hexdigest(), metadata


def automatic(row):
    return {k:json.loads(row[k]) if k in ('box','manifest','spec') else row[k] for k in AUTOMATIC}


def input_key(item):
    return hashlib.sha256(json.dumps(item,sort_keys=True,separators=(',',':')).encode()).hexdigest()


class VegetationBatch:
    def __init__(self, store, data, *, service=None, profile=None):
        self.store = store
        self.service = service or VegetationEvidence(data)
        self.profile, self.metadata = profile or identity()
        with store.connect() as db:
            db.executescript('''
                CREATE TABLE IF NOT EXISTS vegetation_runs (
                    id INTEGER PRIMARY KEY, profile TEXT NOT NULL, metadata TEXT NOT NULL,
                    owner TEXT NOT NULL, state TEXT NOT NULL, ceiling INTEGER NOT NULL,
                    cursor INTEGER NOT NULL DEFAULT 0, total INTEGER NOT NULL,
                    processed INTEGER NOT NULL DEFAULT 0, created REAL NOT NULL,
                    updated REAL NOT NULL, error TEXT);
                CREATE TABLE IF NOT EXISTS vegetation_checks (
                    profile TEXT NOT NULL, poi_id INTEGER NOT NULL REFERENCES pois(id),
                    input_key TEXT NOT NULL, status TEXT NOT NULL, evidence TEXT NOT NULL,
                    elapsed_ms REAL NOT NULL, run_id INTEGER NOT NULL REFERENCES vegetation_runs(id),
                    PRIMARY KEY(profile,poi_id));
                CREATE INDEX IF NOT EXISTS vegetation_queue ON vegetation_checks(profile,status,poi_id);
                CREATE TABLE IF NOT EXISTS vegetation_decisions (
                    profile TEXT NOT NULL, poi_id INTEGER NOT NULL REFERENCES pois(id),
                    input_key TEXT NOT NULL, outcome TEXT NOT NULL, created REAL NOT NULL,
                    PRIMARY KEY(profile,poi_id,input_key));
            ''')

    def scan(self, progress=None):
        """CLI-owned bounded scan; recover the durable cursor after interruption."""
        owner = uuid.uuid4().hex
        with self.store.connect() as db:
            db.execute('BEGIN IMMEDIATE')
            if db.execute("SELECT 1 FROM vegetation_runs WHERE state='running' AND updated>?", (time.time()-300,)).fetchone():
                raise ValueError('A vegetation scan is already running')
            db.execute("UPDATE vegetation_runs SET state='interrupted' WHERE state='running' AND updated<=?",(time.time()-300,))
            run = db.execute("SELECT * FROM vegetation_runs WHERE profile=? AND state IN ('running','interrupted') ORDER BY id DESC LIMIT 1", (self.profile,)).fetchone()
            if run:
                run = dict(run)
                db.execute("UPDATE vegetation_runs SET state='running',owner=?,updated=?,error=NULL WHERE id=?", (owner,time.time(),run['id']))
            else:
                ceiling = db.execute('SELECT coalesce(max(id),0) FROM pois').fetchone()[0]
                total = db.execute(f'SELECT count(*) {JOINS} WHERE {ELIGIBLE} AND p.id<=?',(ceiling,)).fetchone()[0]
                now = time.time()
                rid = db.execute('INSERT INTO vegetation_runs(profile,metadata,owner,state,ceiling,total,created,updated) VALUES(?,?,?,\'running\',?,?,?,?)',
                                 (self.profile,json.dumps(self.metadata),owner,ceiling,total,now,now)).lastrowid
                run = dict(id=rid,ceiling=ceiling,cursor=0,processed=0)
        try:
            while True:
                with self.store.connect() as db:
                    rows = db.execute(f'SELECT {FIELDS} {JOINS} WHERE {ELIGIBLE} AND p.id>? AND p.id<=? ORDER BY p.id LIMIT 100', (run['cursor'],run['ceiling'])).fetchall()
                    cached = {r['poi_id']:dict(r) for r in db.execute('SELECT poi_id,input_key,status FROM vegetation_checks WHERE profile=? AND poi_id>? AND poi_id<=? ORDER BY poi_id LIMIT 1000', (self.profile,run['cursor'],rows[-1]['id'] if rows else run['cursor']))}
                if not rows:break
                results=[]
                for row in rows:
                    item=automatic(row);key=input_key(item);previous=cached.get(row['id'])
                    if previous and previous['input_key']==key and previous['status']!='error':continue
                    start=time.perf_counter()
                    try:
                        result=self.service.inspect(item)
                        status=result['status']
                        evidence=result if status=='candidate' else {k:result[k] for k in ('status','numeric_readings') if k in result}
                    except (OSError,ValueError,RuntimeError) as exc:
                        status='error';evidence={'error':str(exc)}
                    results.append((self.profile,row['id'],key,status,json.dumps(evidence,ensure_ascii=False),(time.perf_counter()-start)*1000,run['id']))
                with self.store.connect() as db:
                    db.execute('BEGIN IMMEDIATE')
                    current=db.execute('SELECT owner,state FROM vegetation_runs WHERE id=?',(run['id'],)).fetchone()
                    if current['owner']!=owner or current['state']!='running':raise RuntimeError('Scan lease changed')
                    db.executemany('INSERT OR REPLACE INTO vegetation_checks VALUES(?,?,?,?,?,?,?)',results)
                    run['cursor']=rows[-1]['id'];run['processed']+=len(rows)
                    db.execute('UPDATE vegetation_runs SET cursor=?,processed=?,updated=? WHERE id=?',(run['cursor'],run['processed'],time.time(),run['id']))
                if progress:progress(self.summary())
            with self.store.connect() as db:
                db.execute("UPDATE vegetation_runs SET state='complete',updated=? WHERE id=? AND owner=?",(time.time(),run['id'],owner))
        except BaseException as exc:
            with self.store.connect() as db:
                db.execute("UPDATE vegetation_runs SET state='interrupted',updated=?,error=? WHERE id=? AND owner=?",(time.time(),str(exc),run['id'],owner))
            raise
        return self.summary()

    def summary(self):
        with self.store.connect() as db:
            run=db.execute('SELECT id,state,total,processed,created,updated,error FROM vegetation_runs WHERE profile=? ORDER BY id DESC LIMIT 1',(self.profile,)).fetchone()
            counts={r['status']:r['n'] for r in db.execute('SELECT status,count(*) n FROM vegetation_checks WHERE profile=? GROUP BY status',(self.profile,))}
            decisions={r['outcome']:r['n'] for r in db.execute('SELECT outcome,count(*) n FROM vegetation_decisions WHERE profile=? GROUP BY outcome',(self.profile,))}
        return dict(profile=self.profile,run=dict(run) if run else None,checks=counts,decisions=decisions)

    def viewer_evidence(self, ids, *, cues_only=False):
        """Current advice for eligible fragments, without running image analysis."""
        ids = list(set(ids))
        results = {}
        with self.store.connect() as db:
            for start in range(0, len(ids), 400):
                subset = ids[start:start+400]
                marks = ','.join('?' for _ in subset)
                evidence = 'NULL evidence' if cues_only else 'c.evidence'
                candidates = "AND c.status='candidate'" if cues_only else ''
                rows = db.execute(f'''SELECT {FIELDS},c.input_key,c.status,{evidence} {JOINS}
                    LEFT JOIN vegetation_checks c ON c.poi_id=p.id AND c.profile=?
                    WHERE {ELIGIBLE} AND p.id IN ({marks}) {candidates}''', [self.profile, *subset]).fetchall()
                decisions = {(r['poi_id'],r['input_key']) for r in db.execute(
                    f'SELECT poi_id,input_key FROM vegetation_decisions WHERE profile=? AND poi_id IN ({marks})', [self.profile,*subset])}
                for row in rows:
                    key = input_key(automatic(row))
                    if (row['id'], key) in decisions:
                        continue
                    if row['input_key'] != key or row['status'] == 'error':
                        results[row['id']] = dict(status='unchecked')
                    else:
                        results[row['id']] = dict(**({'status':row['status']} if cues_only else json.loads(row['evidence'])), profile=self.profile, input_key=key)
        return results

    def decorate_view(self, result):
        """Add cues to actual findings only; selection and cluster counts stay intact."""
        points = list(result['items'])
        map_data = result.get('map', {})
        for entry in map_data.get('items', []):
            point = entry if map_data['mode'] == 'points' else entry.get('item')
            if point is not None:
                points.append(point)
        advice = self.viewer_evidence((p['id'] for p in points), cues_only=True)
        for point in points:
            point['possible_vegetation'] = advice.get(point['id'], {}).get('status') == 'candidate'
        return result

    def pending(self, after=0, limit=24):
        # Walk a small indexed candidate set; input identity is checked before rendering.
        with self.store.connect() as db:
            rows=db.execute(f'''SELECT {FIELDS},c.input_key,c.evidence {JOINS}
                JOIN vegetation_checks c ON c.poi_id=p.id AND c.profile=? AND c.status='candidate'
                WHERE {ELIGIBLE} AND p.id>? AND NOT EXISTS(SELECT 1 FROM vegetation_decisions d
                WHERE d.profile=c.profile AND d.poi_id=c.poi_id AND d.input_key=c.input_key) ORDER BY p.id''',(self.profile,after)).fetchall()
        valid=[r for r in rows if input_key(automatic(r))==r['input_key']]
        items=[]
        for r in valid[:limit]:
            result=json.loads(r['evidence'])
            items.append(dict(id=r['id'],input_key=r['input_key'],source=r['source'],lon=r['lon'],lat=r['lat'],preview=result['preview']))
        return dict(**self.summary(),items=items,remaining=len(valid),next_after=items[-1]['id'] if len(valid)>limit else None)

    def decide(self, profile, items, outcome):
        if profile!=self.profile:raise ValueError('Method changed. Refresh the review queue.')
        if outcome not in ('other','dismiss'):raise ValueError('Unknown review action')
        ids=[r['id'] for r in items]
        if not 1<=len(ids)<=100 or len(ids)!=len(set(ids)):raise ValueError('Select 1 to 100 distinct proposals')
        from .annotations import save
        with self.store.connect() as db:
            db.execute('BEGIN IMMEDIATE')
            for selected in items:
                row=db.execute(f'''SELECT {FIELDS},c.input_key,c.status {JOINS}
                    JOIN vegetation_checks c ON c.poi_id=p.id AND c.profile=? WHERE p.id=? AND {ELIGIBLE}''',(self.profile,selected['id'])).fetchone()
                if (not row or row['status']!='candidate' or row['input_key']!=selected['input_key']
                        or input_key(automatic(row))!=selected['input_key']
                        or db.execute('SELECT 1 FROM vegetation_decisions WHERE profile=? AND poi_id=? AND input_key=?',(self.profile,selected['id'],selected['input_key'])).fetchone()):
                    raise ValueError('A selected proposal changed or was already reviewed. Refresh the queue; nothing was saved.')
            for selected in items:
                if outcome=='other':
                    save(db,selected['id'],dict(ground_truth='',classification='other',map_direction='unknown',member_ids=[selected['id']],sync_reading=False,osm_type='',osm_id=None,osm_name='',note=''),begin=False)
                    db.execute('INSERT INTO reviews(poi_id,verdict,note,created) VALUES(?,\'other\',\'\',?)',(selected['id'],time.time()))
                db.execute('INSERT INTO vegetation_decisions VALUES(?,?,?,?,?)',(self.profile,selected['id'],selected['input_key'],outcome,time.time()))
        return dict(saved=len(items),outcome=outcome)
