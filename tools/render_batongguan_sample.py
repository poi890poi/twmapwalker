"""Download a bounded native historical mosaic and overlay exact OSM segments."""
import hashlib,json,math,sys
from pathlib import Path
from PIL import Image,ImageDraw,ImageFont
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from mapwalker.sources import TileCache
from mapwalker.paths import default_data
from mapwalker.geo import world
from tools.build_osm_segment_review import clipped_runs,midpoint
OUT=ROOT/'evidence/batongguan-review'

def main():
    data=json.loads((OUT/'segments.json').read_text('utf8'))
    chosen=next(s for s in data['segments'] if s['id']==data['default_segment'])
    lat,lon=chosen['mid_latlng'];wx,wy=world(lon,lat,16);x0,y0=math.floor(wx)-2,math.floor(wy)-2
    cache=TileCache(default_data());manifest=[];font=ImageFont.truetype('C:/Windows/Fonts/arialbd.ttf',18)
    for source in ('JM50K_1924_new','JM50K_1916'):
        im=Image.new('RGB',(1024,1024),'white');tiles=[]
        for dy in range(4):
            for dx in range(4):
                path,meta,_=cache.get(source,16,x0+dx,y0+dy);tiles.append(meta)
                with Image.open(path) as tile:im.paste(tile.convert('RGB'),(dx*256,dy*256))
        raw=OUT/f'{source}-original.png';im.save(raw);draw=ImageDraw.Draw(im);ids=[];boxes=[]
        for s in data['segments']:
            points=[[(world(lon,lat,16)[0]-x0)*256,(world(lon,lat,16)[1]-y0)*256] for lat,lon in s['latlngs']]
            runs=clipped_runs(points)
            for run in runs:draw.line([tuple(p) for p in run],fill=s['color'],width=3)
            if not runs:continue
            ids.append(s['id']);p=midpoint(max(runs,key=lambda r:sum(math.dist(a,b) for a,b in zip(r,r[1:]))));x,y=p
            candidates=[]
            for radius in (0,25,45,65,90,120):
                for angle in range(0,360,45):
                    cx=max(30,min(994,x+radius*math.cos(math.radians(angle))));cy=max(14,min(1010,y+radius*math.sin(math.radians(angle))));b=[cx-29,cy-13,cx+29,cy+13]
                    overlap=sum(max(0,min(b[2],c[2])-max(b[0],c[0]))*max(0,min(b[3],c[3])-max(b[1],c[1])) for c in boxes)
                    candidates.append((overlap*1000+radius,b,cx,cy))
            _,b,cx,cy=min(candidates,key=lambda v:v[0]);boxes.append(b)
            draw.line([p,(cx,cy)],fill=s['color'],width=1);draw.rounded_rectangle(b,3,fill='white',outline=s['color'],width=2);draw.text((cx,cy),s['id'],anchor='mm',font=font,fill=s['color'])
        im.save(OUT/f'{source}-sample.png');manifest.append(dict(source=source,z=16,x=x0,y=y0,tiles=tiles,raw_sha256=hashlib.sha256(raw.read_bytes()).hexdigest(),segments=ids))
        print(source,ids,flush=True)
    (OUT/'sample-manifest.json').write_text(json.dumps(manifest,indent=2,ensure_ascii=False),encoding='utf8')

if __name__=='__main__':main()
