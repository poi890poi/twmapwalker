"""SQLite owns job leasing, algorithm identity, publication, and independent reviews."""
import json
import sqlite3
import time
import uuid
from contextlib import contextmanager
from pathlib import Path
from .names import canonical_reading, match_item, match_name, informative, reading_options, UNKNOWN


class Store:
    def __init__(self, path):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self.connect() as db:
            db.executescript('''
            PRAGMA journal_mode=WAL;
            CREATE TABLE IF NOT EXISTS algorithms (
                fingerprint TEXT PRIMARY KEY, name TEXT NOT NULL, version TEXT NOT NULL,
                spec TEXT NOT NULL, active INTEGER NOT NULL DEFAULT 1);
            CREATE TABLE IF NOT EXISTS tiles (
                id INTEGER PRIMARY KEY, source TEXT NOT NULL, z INTEGER NOT NULL,
                x INTEGER NOT NULL, y INTEGER NOT NULL, UNIQUE(source,z,x,y));
            CREATE TABLE IF NOT EXISTS jobs (
                id INTEGER PRIMARY KEY, tile_id INTEGER NOT NULL REFERENCES tiles(id),
                algorithm TEXT NOT NULL REFERENCES algorithms(fingerprint),
                state TEXT NOT NULL DEFAULT 'pending', attempts INTEGER NOT NULL DEFAULT 0,
                token TEXT, lease_until REAL, available_at REAL NOT NULL DEFAULT 0,
                error TEXT, completed_at REAL, telemetry TEXT, manifest TEXT,
                UNIQUE(tile_id,algorithm));
            CREATE INDEX IF NOT EXISTS queue ON jobs(state,available_at);
            CREATE TABLE IF NOT EXISTS attempts (
                id INTEGER PRIMARY KEY, job_id INTEGER NOT NULL, token TEXT NOT NULL,
                started REAL NOT NULL, ended REAL, outcome TEXT, error TEXT);
            CREATE TABLE IF NOT EXISTS pois (
                id INTEGER PRIMARY KEY, job_id INTEGER NOT NULL REFERENCES jobs(id),
                kind TEXT NOT NULL, text TEXT NOT NULL, score REAL NOT NULL,
                lon REAL NOT NULL, lat REAL NOT NULL, box TEXT NOT NULL,
                disposition TEXT NOT NULL, reason TEXT, details TEXT NOT NULL);
            CREATE INDEX IF NOT EXISTS poi_bounds ON pois(lon,lat);
            CREATE INDEX IF NOT EXISTS poi_job ON pois(job_id);
            CREATE TABLE IF NOT EXISTS reviews (
                id INTEGER PRIMARY KEY, poi_id INTEGER NOT NULL REFERENCES pois(id),
                verdict TEXT NOT NULL, note TEXT NOT NULL, created REAL NOT NULL);
            CREATE TABLE IF NOT EXISTS settings (key TEXT PRIMARY KEY, value TEXT NOT NULL);
            CREATE TABLE IF NOT EXISTS readings (
                id INTEGER PRIMARY KEY, poi_id INTEGER NOT NULL REFERENCES pois(id),
                value TEXT NOT NULL, status TEXT NOT NULL, origin TEXT NOT NULL,
                created REAL NOT NULL);
            CREATE INDEX IF NOT EXISTS review_poi ON reviews(poi_id,id);
            CREATE INDEX IF NOT EXISTS reading_poi ON readings(poi_id,id);
            CREATE TABLE IF NOT EXISTS annotations (
                id INTEGER PRIMARY KEY, poi_id INTEGER NOT NULL REFERENCES pois(id),
                payload TEXT NOT NULL, created REAL NOT NULL);
            CREATE INDEX IF NOT EXISTS annotation_poi ON annotations(poi_id,id);
            INSERT OR IGNORE INTO settings VALUES('paused','false');
            CREATE TABLE IF NOT EXISTS foreground (
                id INTEGER PRIMARY KEY CHECK(id=1), source TEXT NOT NULL,
                z INTEGER NOT NULL, xmin INTEGER NOT NULL, xmax INTEGER NOT NULL,
                ymin INTEGER NOT NULL, ymax INTEGER NOT NULL);
            ''')
            # Additive migration for line candidates; existing point data remains valid.
            columns={r['name'] for r in db.execute('PRAGMA table_info(pois)')}
            for name in ('west','south','east','north'):
                if name not in columns:
                    db.execute(f'ALTER TABLE pois ADD COLUMN {name} REAL')

    @contextmanager
    def connect(self):
        db = sqlite3.connect(self.path, timeout=30)
        db.row_factory = sqlite3.Row
        db.execute('PRAGMA foreign_keys=ON')
        try:
            with db:
                yield db
        finally:
            db.close()

    def register(self, specs):
        """The registry is authoritative. New fingerprints backfill every known tile."""
        with self.connect() as db:
            db.execute('BEGIN IMMEDIATE')
            db.execute('UPDATE algorithms SET active=0')
            for spec in specs:
                db.execute('INSERT INTO algorithms VALUES(?,?,?,?,1) ON CONFLICT(fingerprint) DO UPDATE SET active=1',
                           (spec['fingerprint'], spec['name'], spec['version'], json.dumps(spec)))
            db.execute('''INSERT OR IGNORE INTO jobs(tile_id,algorithm)
                          SELECT t.id,a.fingerprint FROM tiles t CROSS JOIN algorithms a WHERE a.active=1''')

    def enqueue(self, source, tiles):
        with self.connect() as db:
            db.execute('BEGIN IMMEDIATE')
            before = db.execute('SELECT COUNT(*) FROM jobs').fetchone()[0]
            for z, x, y in tiles:
                db.execute('INSERT OR IGNORE INTO tiles(source,z,x,y) VALUES(?,?,?,?)', (source,z,x,y))
                db.execute('''INSERT OR IGNORE INTO jobs(tile_id,algorithm)
                    SELECT t.id,a.fingerprint FROM tiles t CROSS JOIN algorithms a
                    WHERE t.source=? AND t.z=? AND t.x=? AND t.y=? AND a.active=1''', (source,z,x,y))
            return db.execute('SELECT COUNT(*) FROM jobs').fetchone()[0] - before

    def pause(self, value):
        with self.connect() as db:
            db.execute("UPDATE settings SET value=? WHERE key='paused'", (json.dumps(value),))

    def focus(self, source, bbox):
        """Replace the shared foreground scope without rewriting job/lease state."""
        from .browse import view_tile_range
        from .sources import SOURCES
        z = SOURCES[source]['max_zoom']
        xs, ys = view_tile_range(bbox, z)
        with self.connect() as db:
            db.execute('INSERT OR REPLACE INTO foreground VALUES(1,?,?,?,?,?,?)',
                       (source,z,xs.start,xs.stop-1,ys.start,ys.stop-1))

    def claim(self, lease=120, now=None, fingerprints=None):
        now = time.time() if now is None else now
        with self.connect() as db:
            db.execute('BEGIN IMMEDIATE')
            if db.execute("SELECT value FROM settings WHERE key='paused'").fetchone()[0] == 'true':
                return None
            expired = db.execute("SELECT id,token,attempts FROM jobs WHERE state='running' AND lease_until<?", (now,)).fetchall()
            for old in expired:
                db.execute("UPDATE attempts SET ended=?,outcome='lease_expired',error='Worker lease expired' WHERE token=?", (now,old['token']))
                db.execute("UPDATE jobs SET state=?,token=NULL,error='Worker lease expired' WHERE id=?",
                           ('failed' if old['attempts'] >= 3 else 'pending',old['id']))
            allowed = '' if fingerprints is None else ' AND j.algorithm IN ('+','.join('?' for _ in fingerprints)+')'
            row = db.execute('''SELECT j.*,t.source,t.z,t.x,t.y,a.name,a.version,a.spec FROM jobs j
                JOIN tiles t ON t.id=j.tile_id JOIN algorithms a ON a.fingerprint=j.algorithm
                WHERE j.state='pending' AND j.available_at<=? AND a.active=1'''+allowed+'''
                ORDER BY CASE WHEN EXISTS (SELECT 1 FROM foreground f
                    WHERE f.source=t.source AND f.z=t.z AND t.x BETWEEN f.xmin AND f.xmax
                    AND t.y BETWEEN f.ymin AND f.ymax) THEN 0 ELSE 1 END, j.id LIMIT 1''',
                [now]+([] if fingerprints is None else list(fingerprints))).fetchone()
            if row is None:
                return None
            token = uuid.uuid4().hex
            db.execute("UPDATE jobs SET state='running',token=?,lease_until=?,attempts=attempts+1 WHERE id=?", (token,now+lease,row['id']))
            db.execute('INSERT INTO attempts(job_id,token,started) VALUES(?,?,?)', (row['id'],token,now))
            return {**dict(row), 'token':token, 'attempts':row['attempts']+1}

    def heartbeat(self, job, lease=120):
        with self.connect() as db:
            return db.execute("UPDATE jobs SET lease_until=? WHERE id=? AND token=? AND state='running'",
                              (time.time()+lease,job['id'],job['token'])).rowcount == 1

    def finish(self, job, pois, telemetry, manifest):
        with self.connect() as db:
            db.execute('BEGIN IMMEDIATE')
            owner = db.execute("SELECT 1 FROM jobs WHERE id=? AND token=? AND state='running' AND lease_until>=?",
                               (job['id'],job['token'],time.time())).fetchone()
            if not owner:
                return False
            for poi in pois:
                coordinates=poi.get('details',{}).get('geometry',{}).get('coordinates',[[poi['lon'],poi['lat']]])
                west=min(p[0] for p in coordinates);east=max(p[0] for p in coordinates)
                south=min(p[1] for p in coordinates);north=max(p[1] for p in coordinates)
                db.execute('''INSERT INTO pois(job_id,kind,text,score,lon,lat,box,disposition,reason,details)
                              VALUES(?,?,?,?,?,?,?,?,?,?)''',
                           (job['id'],poi['kind'],poi.get('text',''),poi['score'],poi['lon'],poi['lat'],
                            json.dumps(poi['box']),poi['disposition'],poi.get('reason'),json.dumps(poi.get('details',{}))))
                db.execute('UPDATE pois SET west=?,south=?,east=?,north=? WHERE id=last_insert_rowid()', (west,south,east,north))
            now = time.time()
            db.execute("UPDATE jobs SET state='complete',completed_at=?,telemetry=?,manifest=?,error=NULL,token=NULL WHERE id=?",
                       (now,json.dumps(telemetry),json.dumps(manifest),job['id']))
            db.execute("UPDATE attempts SET ended=?,outcome='complete' WHERE token=?", (now,job['token']))
            return True

    def fail(self, job, error):
        with self.connect() as db:
            db.execute('BEGIN IMMEDIATE')
            changed = db.execute("""UPDATE jobs SET state=?,error=?,token=NULL,available_at=?
                                 WHERE id=? AND token=? AND state='running'""",
                                 ('failed' if job['attempts']>=3 else 'pending',str(error)[:2000],
                                  time.time()+min(300,10*2**job['attempts']),job['id'],job['token'])).rowcount
            if changed:
                db.execute("UPDATE attempts SET ended=?,outcome='error',error=? WHERE token=?",
                           (time.time(),str(error)[:2000],job['token']))

    def retry_failed(self):
        with self.connect() as db:
            return db.execute("""UPDATE jobs SET state='pending',attempts=0,available_at=0
                WHERE state='failed' AND algorithm IN (SELECT fingerprint FROM algorithms WHERE active=1)""").rowcount

    def status(self):
        with self.connect() as db:
            counts = {r['state']:r['n'] for r in db.execute('''SELECT state,COUNT(*) n FROM jobs j
                       JOIN algorithms a ON a.fingerprint=j.algorithm WHERE a.active=1 GROUP BY state''')}
            return dict(counts=counts, paused=json.loads(db.execute("SELECT value FROM settings WHERE key='paused'").fetchone()[0]),
                tiles=db.execute('SELECT COUNT(*) FROM tiles').fetchone()[0],
                candidates=db.execute("SELECT COUNT(*) FROM pois p JOIN jobs j ON j.id=p.job_id JOIN algorithms a ON a.fingerprint=j.algorithm WHERE a.active=1 AND p.disposition='candidate'").fetchone()[0],
                algorithms=[dict(r) for r in db.execute('SELECT name,version,fingerprint FROM algorithms WHERE active=1')],
                errors=[dict(r) for r in db.execute('''SELECT j.id,j.state,j.error,t.source,t.z,t.x,t.y
                    FROM jobs j JOIN tiles t ON t.id=j.tile_id JOIN algorithms a ON a.fingerprint=j.algorithm
                    WHERE a.active=1 AND j.error IS NOT NULL ORDER BY j.id DESC LIMIT 8''')])

    def pois(self, bbox, source=None, disposition='candidate', limit=500, offset=0, query='',
             kind='all', review='all', reading='all', sort='priority', zoom=None,display='all',display_zoom=15,include_trails=True):
        from .browse import browse
        with self.connect() as db:
            db.execute('BEGIN')
            return browse(db,bbox,source,disposition,limit,offset,query,kind,review,reading,sort,zoom,display,display_zoom,include_trails)

    def coverage(self, bbox, source):
        from .progress import area_progress
        with self.connect() as db:
            db.execute('BEGIN')
            return area_progress(db,bbox,source)

    def poi(self, poi_id):
        with self.connect() as db:
            row = db.execute('''SELECT p.*,t.source,t.z,t.x,t.y,j.algorithm,j.telemetry,j.manifest,a.spec
                FROM pois p JOIN jobs j ON j.id=p.job_id JOIN tiles t ON t.id=j.tile_id
                JOIN algorithms a ON a.fingerprint=j.algorithm WHERE p.id=?''',(poi_id,)).fetchone()
            if row is None:
                return None
            readings=[dict(r) for r in db.execute('SELECT * FROM readings WHERE poi_id=? ORDER BY id',(poi_id,))]
            item={**dict(row),'readings':readings,'reading':readings[-1]['value'] if readings else None,
                  'reading_status':readings[-1]['status'] if readings else None,
                  'reviews':[dict(r) for r in db.execute('SELECT * FROM reviews WHERE poi_id=? ORDER BY id',(poi_id,))]}
            options=reading_options(item);item['display_text']=options[0] if options else ''
            item['annotations']=[dict(r) for r in db.execute('SELECT * FROM annotations WHERE poi_id=? ORDER BY id',(poi_id,))]
            for annotation in item['annotations']:
                annotation['payload']=json.loads(annotation['payload'])
            item['annotation']=item['annotations'][-1]['payload'] if item['annotations'] else {}
            return item

    def save_annotation(self,poi_id,payload):
        members=sorted(set([poi_id]+payload.pop('fragment_ids',[])))
        with self.connect() as db:
            rows=db.execute('SELECT p.id,t.source FROM pois p JOIN jobs j ON j.id=p.job_id JOIN tiles t ON t.id=j.tile_id WHERE p.id IN ('+','.join('?' for _ in members)+')',members).fetchall()
            if len(rows)!=len(members):raise ValueError('A fragment ID does not exist.')
            if len({r['source'] for r in rows})!=1:raise ValueError('Fragments must belong to the same historical map series.')
            if len(members)>1:
                # Reuse an existing group; merging updates every existing member atomically.
                latest=db.execute('SELECT payload FROM annotations WHERE poi_id=? ORDER BY id DESC LIMIT 1',(poi_id,)).fetchone()
                group=json.loads(latest['payload']).get('group_id') if latest else None
                group=group or str(uuid.uuid4())
                for row in db.execute('SELECT a.poi_id,a.payload FROM annotations a WHERE a.id=(SELECT MAX(b.id) FROM annotations b WHERE b.poi_id=a.poi_id)').fetchall():
                    previous=json.loads(row['payload'])
                    if row['poi_id'] in members or previous.get('group_id')==group:
                        other_group=previous.get('group_id')
                        if other_group:
                            for other in db.execute('SELECT a.poi_id,a.payload FROM annotations a WHERE a.id=(SELECT MAX(b.id) FROM annotations b WHERE b.poi_id=a.poi_id)').fetchall():
                                if json.loads(other['payload']).get('group_id')==other_group:members.append(other['poi_id'])
                members=sorted(set(members))
            else:
                latest=db.execute('SELECT payload FROM annotations WHERE poi_id=? ORDER BY id DESC LIMIT 1',(poi_id,)).fetchone()
                group=json.loads(latest['payload']).get('group_id') if latest else None
            payload['group_id']=group
            for member in members:
                if member==poi_id: value=payload
                else:
                    latest=db.execute('SELECT payload FROM annotations WHERE poi_id=? ORDER BY id DESC LIMIT 1',(member,)).fetchone()
                    value=json.loads(latest['payload']) if latest else {}
                    value['group_id']=group
                db.execute('INSERT INTO annotations(poi_id,payload,created) VALUES(?,?,?)',(member,json.dumps(value,ensure_ascii=False),time.time()))
            return payload

    def latest_annotations(self,poi_ids):
        result={}
        with self.connect() as db:
            for start in range(0,len(poi_ids),500):
                batch=poi_ids[start:start+500]
                rows=db.execute('SELECT a.poi_id,a.payload FROM annotations a WHERE a.poi_id IN ('+','.join('?' for _ in batch)+') AND a.id=(SELECT MAX(b.id) FROM annotations b WHERE b.poi_id=a.poi_id)',batch)
                result.update({r['poi_id']:json.loads(r['payload']) for r in rows})
        return result

    def save_reading(self,poi_id,value,status='tentative',origin='manual'):
        value=canonical_reading(value)
        if len(value)>80:raise ValueError('A reading can contain at most 80 characters.')
        if status not in ('tentative','confirmed'):raise ValueError('Unknown reading status.')
        if status=='confirmed' and (not value or UNKNOWN in value):
            raise ValueError('A verified reading must be complete. Keep ? readings tentative.')
        with self.connect() as db:
            db.execute('INSERT INTO readings(poi_id,value,status,origin,created) VALUES(?,?,?,?,?)',
                       (poi_id,value,status,origin,time.time()))
        return value

    def name_suggestions(self,poi_id,query=''):
        item=self.poi(poi_id)
        if item is None:return None
        options=reading_options(item);out=[];seen=set()
        def consider(value,source,origin,other_id=None):
            value=canonical_reading(value)
            if not value or UNKNOWN in value or value in seen:return
            matches=[m for reading in options if len(canonical_reading(value))>=len(canonical_reading(reading))
                     and (m:=match_name(reading,value))]
            if not matches:return
            if any(canonical_reading(reading)==value for reading in options):return
            best=max(matches,key=lambda m:m['score']);seen.add(value)
            out.append(dict(name=value,source=source,origin=origin,poi_id=other_id,
                            score=best['score'],verified=False))
        if query:consider(query,'Your search; unverified','search-suggestion')
        # A bounded local corpus, not a gazetteer or a historical-coordinate correction.
        nearby=self.pois((max(118,item['lon']-.1),max(21.5,item['lat']-.1),
                         min(123,item['lon']+.1),min(26,item['lat']+.1)),item['source'],limit=2000)
        for other in nearby['items']:
            if other['id']==poi_id or other.get('review')=='rejected':continue
            if not other.get('reading') and (other['kind']!='text' or other['score']<.45):continue
            for value in reading_options(other):
                consider(value,'Nearby saved reading' if other.get('reading') else 'Nearby OCR; unverified',
                         'local-suggestion',other['id'])
        out.sort(key=lambda p:(p['origin']!='search-suggestion',-p['score'],p['name']))
        return dict(items=out[:8],scope='Your search and nearby local readings in this map series. Suggestions are not historical identification.',
                    truncated=nearby['total']>2000)

    def review(self, poi_id, verdict, note):
        with self.connect() as db:
            db.execute('INSERT INTO reviews(poi_id,verdict,note,created) VALUES(?,?,?,?)', (poi_id,verdict,note,time.time()))
