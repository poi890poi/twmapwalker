"""Isolated browser fixture. No synthetic readings are written to production."""
import sys,json,shutil
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from mapwalker.app import create_app
from mapwalker.sources import TileCache,SNAPSHOT
from mapwalker.paths import default_data
from mapwalker.detectors import CONFIG
from mapwalker.geo import pixel_lonlat
from starlette.routing import Route
from starlette.responses import FileResponse
import uvicorn

data=ROOT/'data/name-review';data.mkdir(exist_ok=True)
# Copy only the existing cache; isolated review requests may add their own tiles.
shutil.copytree(default_data()/'tiles',data/'tiles',dirs_exist_ok=True)
spec=dict(fingerprint='uncertain-name-ui-fixture',name='text',version='fixture',config=CONFIG,snapshot=SNAPSHOT)
app=create_app(data,worker_enabled=False,registry=[spec]);store=app.state.store
if not store.status()['tiles']:
 store.enqueue('JM50K_1924_new',[(16,54896,28092)]);job=store.claim();cache=TileCache(data)
 manifest=[]
 for source in ['JM50K_1924_new','EMAP']:
  _,entries,_=cache.mosaic(source,16,54896,28092);manifest+=entries
 lon,lat=pixel_lonlat(16,54896,28092,45,125)
 store.finish(job,[dict(kind='text',text='?ライ社',score=.4,lon=lon,lat=lat,box=[20,32,75,255],disposition='candidate',details=dict(fixture=True,developed_overlap=0,angle_degrees_ccw=0)),
                   dict(kind='text',text='ロライ社',score=.4,lon=lon+.0005,lat=lat+.0005,box=[25,30,70,85],disposition='candidate',details=dict(fixture=True,developed_overlap=0,angle_degrees_ccw=0))],{'fixture':'UI flow only, not model output'},manifest)
markup=(ROOT/'web/index.html').read_text('utf-8').replace('<body>','<body><div style="position:fixed;z-index:9999;top:0;left:50%;transform:translateX(-50%);background:#fff2ba;color:#603b00;padding:4px 12px;font:12px sans-serif">TEST FIXTURE — sample readings, not detection results</div>')
page=data/'review.html';page.write_text(markup,'utf-8')
async def index(request):return FileResponse(page)
app.router.routes.insert(0,Route('/',index))
if __name__=='__main__':uvicorn.run(app,host='127.0.0.1',port=8766)
