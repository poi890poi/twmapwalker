import io
import json
import re
import threading
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Literal

from fastapi import Depends, FastAPI, HTTPException, Query, Request
from fastapi.responses import FileResponse, Response
from fastapi.staticfiles import StaticFiles
from PIL import Image, ImageDraw
from pydantic import BaseModel, Field
from starlette.middleware.trustedhost import TrustedHostMiddleware

from .db import Store
from .detectors import developed_mask, specs
from .geo import lonlat
from .browse import view_tile_range as tile_range, view_tiles as tiles, validate_view_bbox as validate_bbox
from .sources import HISTORICAL, SOURCES, TileCache
from .worker import Worker
from .paths import default_data
from .osm import OSMContext
from .auth import AccessConfig, install_access
from urllib.parse import urlsplit

ROOT = Path(__file__).resolve().parents[1]


class Plan(BaseModel):
    bbox: list[float] = Field(min_length=4,max_length=4)
    sources: list[Literal['JM50K_1916','JM50K_1924_new']] = Field(default_factory=lambda:list(HISTORICAL),min_length=1,max_length=2)


class Review(BaseModel):
    verdict: Literal['confirmed','rejected','uncertain']
    note: str = Field(default='',max_length=2000)


class Pause(BaseModel):
    paused: bool


class Reading(BaseModel):
    value: str = Field(max_length=80)
    status: Literal['tentative','confirmed'] = 'tentative'
    origin: Literal['manual','search-suggestion','local-suggestion'] = 'manual'


def bounds(raw):
    try:
        return validate_bbox([float(v) for v in raw.split(',')])
    except (ValueError,TypeError) as exc:
        raise HTTPException(400,str(exc)) from exc


def browse_filters(kind: Literal['all','text','symbol','trail']='all',
                   review: Literal['all','unreviewed','confirmed','rejected','uncertain']='all',
                   reading: Literal['all','named','unread']='all',
                   sort: Literal['priority','name','newest','score']='priority'):
    return dict(kind=kind,review=review,reading=reading,sort=sort)


def create_app(data=None, worker_enabled=True, registry=None, access_config=None):
    access_config=access_config or AccessConfig()
    access_config.validate()
    data = Path(data or default_data())
    store = Store(data/'mapwalker.sqlite3')
    store.register(specs() if registry is None else registry)
    cache = TileCache(data)
    worker = Worker(store,cache)
    osm = OSMContext(data,recover=worker_enabled)

    @asynccontextmanager
    async def lifespan(app):
        thread = threading.Thread(target=worker.run,daemon=True,name='mapwalker-worker')
        osm_thread = threading.Thread(target=osm.run,daemon=True,name='osm-supporting-context')
        if worker_enabled:
            thread.start()
            osm_thread.start()
        yield
        worker.stop.set()
        osm.stop.set()
        if worker_enabled:
            thread.join(timeout=2)
            osm_thread.join(timeout=2)

    app = FastAPI(title='Mapwalker',lifespan=lifespan)
    app.state.store = store
    app.state.cache = cache
    app.state.osm = osm
    hosts=['127.0.0.1','localhost','testserver']
    if access_config.enabled:hosts.append(urlsplit(access_config.origin).hostname)
    app.add_middleware(TrustedHostMiddleware,allowed_hosts=hosts)

    @app.middleware('http')
    async def same_origin(request: Request, call_next):
        if request.method in ('POST','PUT','DELETE'):
            origin = request.headers.get('origin')
            expected = access_config.origin if access_config.enabled else f'{request.url.scheme}://{request.headers.get("host")}'
            if origin and origin != expected:
                return Response('Cross-origin writes are disabled',status_code=403)
        response = await call_next(request)
        response.headers['X-Content-Type-Options'] = 'nosniff'
        return response

    install_access(app,data,access_config)

    @app.get('/api/sources')
    def sources():
        return dict(sources=SOURCES,snapshot=cache.root.name,max_tiles_per_plan=2500)

    @app.get('/api/status')
    def status():
        return store.status()

    @app.get('/api/osm/context')
    def osm_context(lon: float=Query(ge=118,le=123),lat: float=Query(ge=21.5,le=26.5),
                    radius: int=Query(1000,ge=100,le=1000)):
        try:return osm.context(lon,lat,radius)
        except (OSError,ValueError) as exc:raise HTTPException(503,str(exc)) from exc

    @app.get('/api/osm/snapshot/{digest}')
    def osm_snapshot(digest: str):
        if not re.fullmatch('[0-9a-f]{64}',digest):raise HTTPException(404,'Unknown OSM snapshot')
        path=osm.root/'snapshots'/f'{digest}.json'
        if not path.is_file():raise HTTPException(404,'Unknown OSM snapshot')
        return FileResponse(path,media_type='application/json')

    def estimate(plan):
        try:
            validate_bbox(plan.bbox)
        except ValueError as exc:
            raise HTTPException(400,str(exc)) from exc
        counts = {}
        for source in set(plan.sources):
            xs,ys = tile_range(plan.bbox,SOURCES[source]['max_zoom'])
            counts[source] = len(xs)*len(ys)
        count = sum(counts.values())
        return dict(tiles=count,by_source=counts,max_zoom=16,
                    jobs=count*len(store.status()['algorithms']),allowed=count<=2500)

    @app.post('/api/plan/estimate')
    def plan_estimate(plan: Plan):
        return estimate(plan)

    @app.post('/api/plan')
    def plan_create(plan: Plan):
        quote = estimate(plan)
        if not quote['allowed']:
            raise HTTPException(400,'Zoom in: a web batch is limited to 2,500 historical tiles. Use CLI batches for larger regions.')
        count = sum(store.enqueue(s,tiles(plan.bbox,SOURCES[s]['max_zoom'])) for s in set(plan.sources))
        return dict(added_jobs=count,**quote)

    @app.post('/api/worker/pause')
    def pause(payload: Pause):
        store.pause(payload.paused)
        return store.status()

    @app.post('/api/worker/retry')
    def retry():
        return dict(retried=store.retry_failed())

    @app.get('/api/pois')
    def pois(bbox: str, source: Literal['JM50K_1916','JM50K_1924_new'] | None=None,
             disposition: Literal['candidate','excluded','all']='candidate',
             limit: int=Query(500,ge=1,le=1000),offset: int=Query(0,ge=0),q: str=Query('',max_length=80),
             filters: dict=Depends(browse_filters)):
        return store.pois(bounds(bbox),source,disposition,limit,offset,query=q,**filters)

    @app.get('/api/browse')
    def browse(bbox: str,source: Literal['JM50K_1916','JM50K_1924_new'] | None=None,
               disposition: Literal['candidate','excluded','all']='candidate',
               limit: int=Query(50,ge=1,le=1000),offset: int=Query(0,ge=0),
               q: str=Query('',max_length=80),zoom: int=Query(15,ge=5,le=19),
               filters: dict=Depends(browse_filters)):
        return store.pois(bounds(bbox),source,disposition,limit,offset,query=q,zoom=zoom,**filters)

    @app.get('/api/pois/{poi_id}/suggestions')
    def suggestions(poi_id: int,q: str=Query('',max_length=80)):
        result=store.name_suggestions(poi_id,q)
        if result is None:raise HTTPException(404,'Candidate not found')
        return result

    @app.post('/api/pois/{poi_id}/reading')
    def reading(poi_id: int,payload: Reading):
        if store.poi(poi_id) is None:raise HTTPException(404,'Candidate not found')
        try:value=store.save_reading(poi_id,payload.value,payload.status,payload.origin)
        except ValueError as exc:raise HTTPException(400,str(exc)) from exc
        return dict(saved=True,value=value,status=payload.status)

    @app.get('/api/pois/{poi_id}')
    def detail(poi_id: int):
        item = store.poi(poi_id)
        if item is None:
            raise HTTPException(404,'Candidate not found')
        for field in ('box','details','telemetry','manifest','spec'):
            item[field] = json.loads(item[field])
        return item

    @app.post('/api/pois/{poi_id}/review')
    def review(poi_id: int,payload: Review):
        if store.poi(poi_id) is None:
            raise HTTPException(404,'Candidate not found')
        store.review(poi_id,payload.verdict,payload.note)
        return dict(saved=True)

    @app.get('/api/pois/{poi_id}/image')
    def evidence_image(poi_id: int,kind: Literal['historic','modern','mask']='historic',thumbnail: bool=False):
        item = detail(poi_id)
        old_cache = TileCache(data,snapshot=item['spec']['snapshot'])
        source = item['source'] if kind=='historic' else 'EMAP'
        try:
            image, manifest, _ = old_cache.mosaic(source,item['z'],item['x'],item['y'])
            expected = {(m['source'],m['z'],m['x'],m['y']):m['sha256'] for m in item['manifest']}
            if any(expected.get((m['source'],m['z'],m['x'],m['y']))!=m['sha256'] for m in manifest):
                raise ValueError('Original evidence input hash mismatch')
        except Exception as exc:
            raise HTTPException(503,f'Evidence unavailable: {exc}') from exc
        if kind=='mask':
            mask = Image.fromarray((developed_mask(image,item['spec']['config'])*140).astype('uint8'))
            image.paste(Image.new('RGB',image.size,'#d54e47'),mask=mask)
        box = [v+64 for v in item['box']]
        if thumbnail:
            cx,cy = (box[0]+box[2])/2,(box[1]+box[3])/2
            radius = max(35,(box[2]-box[0])/2+12,(box[3]-box[1])/2+12)
            image = image.crop((int(cx-radius),int(cy-radius),int(cx+radius),int(cy+radius))).resize((112,112))
        else:
            ImageDraw.Draw(image).rectangle(box,outline='#e54926',width=2)
            if item['kind']=='trail':
                ImageDraw.Draw(image).line([tuple(point) for point in item['details']['pixel_path']],fill='#7550ae',width=3)
        stream = io.BytesIO()
        image.save(stream,format='PNG')
        return Response(stream.getvalue(),media_type='image/png')

    @app.get('/api/tiles/{source}/{z}/{x}/{y}')
    def tile(source: str,z: int,x: int,y: int):
        if source not in SOURCES:
            raise HTTPException(404,'Unknown map source')
        try:
            path,meta,_ = cache.get(source,z,x,y)
        except ValueError as exc:
            raise HTTPException(400,str(exc)) from exc
        except Exception as exc:
            raise HTTPException(502,f'Map source unavailable: {exc}') from exc
        return FileResponse(path,media_type=meta['content_type'],headers={'Cache-Control':'public,max-age=86400'})

    @app.get('/api/jobs')
    def jobs(limit: int=Query(100,ge=1,le=500)):
        with store.connect() as db:
            return [dict(r) for r in db.execute('''SELECT j.id,j.state,j.attempts,j.error,j.telemetry,
                t.source,t.z,t.x,t.y,a.name,a.version,a.fingerprint FROM jobs j
                JOIN tiles t ON t.id=j.tile_id JOIN algorithms a ON a.fingerprint=j.algorithm
                WHERE a.active=1 ORDER BY j.id DESC LIMIT ?''',(limit,))]

    @app.get('/api/coverage')
    def coverage(bbox: str,source: str):
        if source not in HISTORICAL:
            raise HTTPException(400,'Unknown historical source')
        xs,ys = tile_range(bounds(bbox),SOURCES[source]['max_zoom'])
        with store.connect() as db:
            rows = db.execute('''SELECT t.z,t.x,t.y,
                SUM(CASE WHEN j.state='complete' THEN 1 ELSE 0 END) complete,COUNT(*) total
                FROM tiles t JOIN jobs j ON j.tile_id=t.id JOIN algorithms a ON a.fingerprint=j.algorithm
                WHERE a.active=1 AND t.source=? AND t.x>=? AND t.x<=? AND t.y>=? AND t.y<=?
                GROUP BY t.id LIMIT 2500''',(source,xs.start,xs.stop-1,ys.start,ys.stop-1)).fetchall()
            return [dict(**dict(r),bounds=[lonlat(r['x'],r['y']+1,r['z']),lonlat(r['x']+1,r['y'],r['z'])]) for r in rows]

    @app.get('/api/coverage-summary')
    def coverage_summary(bbox: str,source: str):
        if source not in HISTORICAL:
            raise HTTPException(400,'Unknown historical source')
        z=SOURCES[source]['max_zoom']
        xs,ys=tile_range(bounds(bbox),z)
        total=len(xs)*len(ys)
        with store.connect() as db:
            row=db.execute('''SELECT COUNT(*) known,COALESCE(SUM(CASE WHEN done=required THEN 1 ELSE 0 END),0) complete
                FROM (SELECT t.id,SUM(CASE WHEN j.state='complete' THEN 1 ELSE 0 END) done,COUNT(*) required
                FROM tiles t JOIN jobs j ON j.tile_id=t.id JOIN algorithms a ON a.fingerprint=j.algorithm
                WHERE a.active=1 AND t.source=? AND t.z=? AND t.x>=? AND t.x<=? AND t.y>=? AND t.y<=?
                GROUP BY t.id)''',(source,z,xs.start,xs.stop-1,ys.start,ys.stop-1)).fetchone()
        return dict(total=total,complete=row['complete'],queued_or_running=row['known']-row['complete'],
                    not_queued=total-row['known'])

    @app.get('/api/export')
    def export(bbox: str,source: Literal['JM50K_1916','JM50K_1924_new'],q: str=Query('',max_length=80),
               disposition: Literal['candidate','excluded','all']='candidate',filters: dict=Depends(browse_filters)):
        result = store.pois(bounds(bbox),source,disposition,limit=10000,query=q,**filters)
        if result['total']>10000 or result.get('search_truncated'):
            raise HTTPException(400,'Zoom in to export at most 10,000 candidates')
        features = [dict(type='Feature',geometry=json.loads(p['details']).get('geometry',dict(type='Point',coordinates=[p['lon'],p['lat']])),
                         properties={k:v for k,v in p.items() if k not in ('lon','lat')}) for p in result['items']]
        return Response(json.dumps(dict(type='FeatureCollection',features=features),ensure_ascii=False),
                        media_type='application/geo+json',headers={'Content-Disposition':'attachment; filename="mapwalker-pois.geojson"'})

    app.mount('/evidence',StaticFiles(directory=ROOT/'evidence',html=True),name='evidence')
    app.mount('/',StaticFiles(directory=ROOT/'web',html=True),name='web')
    return app
