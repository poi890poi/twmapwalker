"""Disposable offline browser fixture: python -m tools.preview_inspector.

Uses the real app and annotation database paths, with synthetic map imagery only.
Never reads or writes the user's findings. Stop with Ctrl+C.
"""
import io
import tempfile
from pathlib import Path

import uvicorn
from fastapi import Response
from fastapi.routing import APIRoute
from PIL import Image, ImageDraw

from mapwalker.app import create_app
from mapwalker.geo import world, pixel_lonlat


def main():
    with tempfile.TemporaryDirectory(prefix='mapwalker-inspector-') as directory:
        spec=dict(fingerprint='inspector-fixture',name='text',version='test',config={},snapshot='test')
        app=create_app(Path(directory),worker_enabled=False,registry=[spec])
        x,y=map(int,world(121.55,24.86,16))
        store=app.state.store
        store.enqueue('JM50K_1916',[(16,x,y)])
        job=store.claim()
        rows=[]
        for index,box in enumerate([[20,60,90,105],[130,60,200,105]]):
            lon,lat=pixel_lonlat(16,x,y,(box[0]+box[2])/2,(box[1]+box[3])/2)
            rows.append(dict(kind='text',text=f'Inspector fixture {index+1}',score=.99,lon=lon,lat=lat,box=box,disposition='candidate',details={}))
        store.finish(job,rows,{},[])
        image=Image.new('RGB',(256,256),'#f4efdd')
        draw=ImageDraw.Draw(image)
        for line in range(0,256,32):draw.line([(0,line),(256,line+25)],fill='#b7aa83',width=2)
        draw.text((20,70),'INSPECTOR TEST MAP',fill='#193332')
        data=io.BytesIO();image.save(data,format='PNG');png=data.getvalue()

        def image_response():return Response(png,media_type='image/png')
        def osm_response():return dict(state='complete',features=[],total=0,truncated=False,radius_m=1000,note='Synthetic fixture; no external requests.',retrieved_at=None,stale=False)
        app.router.routes.insert(0,APIRoute('/api/pois/{poi_id}/image',image_response,methods=['GET']))
        app.router.routes.insert(0,APIRoute('/api/tiles/{source}/{z}/{x}/{y}',image_response,methods=['GET']))
        app.router.routes.insert(0,APIRoute('/api/osm/context',osm_response,methods=['GET']))
        uvicorn.run(app,host='127.0.0.1',port=8776,log_level='warning')


if __name__=='__main__':main()
