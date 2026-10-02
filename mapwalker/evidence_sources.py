"""Optional, local, checksummed gazetteer and native-resolution terrain readers."""
import csv
import hashlib
import json
import math
import re
from functools import lru_cache
from pathlib import Path

from .osm import distance_m


class LocalEvidence:
    def __init__(self, data):
        self.root=Path(data)/'multi-evidence'

    @lru_cache(maxsize=4)
    def _verified(self, name):
        manifest=json.loads((self.root/'sources.json').read_text('utf-8'))
        entry=manifest[name];path=self.root/entry['file']
        if path.resolve().parent!=self.root.resolve():raise ValueError('Evidence path must be inside its data directory')
        with path.open('rb') as f:digest=hashlib.file_digest(f,'sha256').hexdigest()
        if digest!=entry['sha256']:raise ValueError('Evidence source hash mismatch')
        return path,entry,path.stat().st_mtime_ns,path.stat().st_size

    def source(self,name):
        path,entry,mtime,size=self._verified(name)
        stat=path.stat()
        if (stat.st_mtime_ns,stat.st_size)!=(mtime,size):raise ValueError('Evidence file changed; restart after installing its new manifest')
        return path,entry

    @lru_cache(maxsize=1)
    def _gazetteer(self):
        path,_=self.source('gazetteer');cells={}
        with path.open(encoding='utf-8-sig',newline='') as stream:
            for number,row in enumerate(csv.DictReader(stream),2):
                try:lon,lat=float(row['Longitude']),float(row['Latitude'])
                except (ValueError,TypeError):continue
                if not (118<=lon<=123 and 21.5<=lat<=26.5):continue
                names=[v.strip() for v in re.split('[;；、\n]',row['AnotherName']) if v.strip()]
                feature=dict(type='Feature',geometry=dict(type='Point',coordinates=[lon,lat]),properties=dict(
                    provider='moi',record_id=number,name=row['PlaceName'],aliases=names,category=row['Type'],
                    url='https://data.gov.tw/dataset/40456',tags={},data_source=row['DataSource']))
                cells.setdefault((math.floor(lon*50),math.floor(lat*50)),[]).append(feature)
        return cells

    def nearby(self,lon,lat,radius=1000):
        try:
            _,entry=self.source('gazetteer');cells=self._gazetteer()
            x,y=math.floor(lon*50),math.floor(lat*50)
            nearby=[f for dx in (-1,0,1) for dy in (-1,0,1) for f in cells.get((x+dx,y+dy),[])
                    if distance_m(f['geometry'],lon,lat)<=radius]
            return nearby,dict(state='available',count=len(nearby),**entry)
        except (OSError,ValueError,KeyError) as exc:
            return [],dict(state='unavailable',reason=str(exc))

    def point(self,lon,lat):
        try:
            path,entry=self.source('terrain')
            return self._point(str(path),lon,lat,entry['sha256'])
        except (OSError,ValueError,KeyError,ImportError) as exc:
            return dict(state='unavailable',reason=str(exc))

    def terrain_status(self):
        try:
            import rasterio
            path,entry=self.source('terrain')
            with rasterio.open(path) as raster:
                if not raster.crs or not raster.crs.is_projected or raster.crs.linear_units!='metre':
                    raise ValueError('Terrain requires a projected metre CRS')
                resolution=max(map(abs,raster.res))
                if not 1<=resolution<=30:raise ValueError('Unsupported native terrain resolution')
            return dict(state='available',native_resolution_m=resolution,**entry)
        except (OSError,ValueError,KeyError,ImportError) as exc:
            return dict(state='unavailable',reason=str(exc))

    @lru_cache(maxsize=1024)
    def _point(self,path,lon,lat,digest):
        import numpy as np
        import rasterio
        from rasterio.warp import transform
        from rasterio.windows import Window
        with rasterio.open(path) as raster:
            if not raster.crs or not raster.crs.is_projected:raise ValueError('Terrain requires a projected metre CRS')
            if raster.crs.linear_units!='metre':raise ValueError('Terrain horizontal units must be metres')
            resolution=max(abs(raster.res[0]),abs(raster.res[1]))
            if not 1<=resolution<=30:raise ValueError('Unsupported native terrain resolution')
            x,y=transform('EPSG:4326',raster.crs,[lon],[lat]);row,col=raster.index(x[0],y[0])
            if not (0<=row<raster.height and 0<=col<raster.width):return dict(state='outside-coverage')
            radius=math.ceil(120/resolution)
            values=raster.read(1,window=Window(col-radius,row-radius,2*radius+1,2*radius+1),masked=True,boundless=True)
            center=values[radius,radius]
            if np.ma.is_masked(center) or not np.isfinite(center):return dict(state='nodata')
            yy,xx=np.ogrid[-radius:radius+1,-radius:radius+1]
            circle=(xx*raster.res[0])**2+(yy*raster.res[1])**2<=120**2
            valid=circle&~np.ma.getmaskarray(values)&np.isfinite(values.data)
            fraction=float(valid.sum()/circle.sum())
            heights=values.data[valid]
            return dict(state='available',elevation_m=round(float(center),1),native_resolution_m=resolution,
                local_radius_m=120,valid_fraction=round(fraction,3),
                local_max_m=round(float(heights.max()),1),
                below_local_max_m=round(float(heights.max()-center),1),
                peak_like=bool(fraction>=.95 and heights.max()-center<=10),
                meaning='Terrain near the modern coordinate; peak-like relief is not proof of a historical peak',sha256=digest)
