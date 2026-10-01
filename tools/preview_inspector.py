"""Disposable offline browser fixture: python -m tools.preview_inspector.

Uses the real app and annotation database paths, with synthetic map imagery only.
Never reads or writes the user's findings. Stop with Ctrl+C.
"""
import io
import argparse
import tempfile
from pathlib import Path

import uvicorn
from fastapi import Response
from fastapi.routing import APIRoute
from PIL import Image, ImageDraw, ImageFont

from mapwalker.app import create_app
from mapwalker.geo import world, pixel_lonlat
from mapwalker.osm import distance_m


def main():
    parser=argparse.ArgumentParser();parser.add_argument('--direction',action='store_true');parser.add_argument('--symbols',action='store_true')
    args=parser.parse_args();direction=args.direction
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
            rows.append(dict(kind='symbol' if args.symbols else 'text',text='' if args.symbols else ['社','烏'][index] if direction else f'Inspector fixture {index+1}',score=.99,lon=lon,lat=lat,box=box,disposition='candidate',details={}))
        store.finish(job,rows,{},[])
        image=Image.new('RGB',(256,256),'#f4efdd')
        draw=ImageDraw.Draw(image)
        for line in range(0,256,32):draw.line([(0,line),(256,line+25)],fill='#b7aa83',width=2)
        if args.symbols:
            for cx in (55,165):draw.polygon([(cx,65),(cx+17,95),(cx-17,95)],fill='#193332')
        elif direction:
            font_path=Path('C:/Windows/Fonts/msjh.ttc')
            font=ImageFont.truetype(str(font_path),32) if font_path.exists() else ImageFont.load_default()
            for x_pos,glyph in [(36,'社'),(99,'來'),(146,'烏')]:draw.text((x_pos,65),glyph,font=font,fill='#193332')
        else:draw.text((20,70),'INSPECTOR TEST MAP',fill='#193332')
        data=io.BytesIO();image.save(data,format='PNG');png=data.getvalue()

        def image_response():return Response(png,media_type='image/png')
        def osm_response(lon: float=rows[0]['lon'],lat: float=rows[0]['lat'],radius: int=1000):
            features=[dict(type='Feature',geometry=dict(type='Point',coordinates=[rows[0]['lon']+.002,rows[0]['lat']]),
                properties=dict(osm_type='node',osm_id=123,name='烏來社',tags={'place':'village','name':'烏來社'},category='place',url='https://www.openstreetmap.org/node/123')),
                dict(type='Feature',geometry=dict(type='MultiLineString',coordinates=[[[rows[0]['lon']-.003,rows[0]['lat']],[rows[0]['lon']+.003,rows[0]['lat']]]]),
                properties=dict(osm_type='way',osm_id=456,name='Nearby trail',tags={'highway':'path'},category='trail',url='https://www.openstreetmap.org/way/456'))]
            for f in features:f['properties']['distance_m']=round(distance_m(f['geometry'],lon,lat))
            return dict(state='complete',features=features,total=2,truncated=False,radius_m=1000,note='Synthetic fixture; no external requests.',retrieved_at=None,stale=False)
        app.state.osm.context=osm_response
        app.router.routes.insert(0,APIRoute('/api/pois/{poi_id}/image',image_response,methods=['GET']))
        app.router.routes.insert(0,APIRoute('/api/tiles/{source}/{z}/{x}/{y}',image_response,methods=['GET']))
        app.router.routes.insert(0,APIRoute('/api/osm/context',osm_response,methods=['GET']))
        uvicorn.run(app,host='127.0.0.1',port=8776,log_level='warning')


if __name__=='__main__':main()
