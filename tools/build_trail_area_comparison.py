"""Native, unregistered original/OSM pairs at independently selected trail areas."""
import hashlib,json,math,sys
from pathlib import Path
from PIL import Image,ImageDraw,ImageFont
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from mapwalker.geo import world,lonlat
from mapwalker.osm import lines
from mapwalker.sources import TileCache,HISTORICAL
from mapwalker.paths import default_data
from tools.build_osm_segment_review import clipped_runs,split_run,midpoint,COLORS
OUT=ROOT/'evidence/trail-area-comparison'

def pixel_lines(way):
    return [[[x*256,y*256] for x,y in (world(lon,lat,16) for lon,lat in line)] for line in lines(way.get('geometry',[]))]

def length(line):return sum(math.dist(a,b) for a,b in zip(line,line[1:]))

def select_areas(payload):
    areas=[]
    for prefix,name in [('H','哈盆越嶺步道'),('N','能高越嶺古道'),('J','浸水營古道')]:
        ways=sorted([w for w in payload['elements'] if w.get('tags',{}).get('name')==name and w['tags'].get('highway') in ('path','footway','track')],key=lambda w:w['id'])
        anchor=max(((length(line),w['id'],line) for w in ways for line in pixel_lines(w)),key=lambda t:t[0])
        x,y=midpoint(anchor[2]);x0,y0=math.floor(x/256)-2,math.floor(y/256)-2
        west,north=lonlat(x0,y0,16);east,south=lonlat(x0+4,y0+4,16)
        segments=[]
        for wi,w in enumerate(ways):
            for line in pixel_lines(w):
                for run in clipped_runs([[x-x0*256,y-y0*256] for x,y in line]):
                    for piece in split_run(run,180):
                        mid=midpoint(piece)
                        segments.append(dict(id=f'{prefix}{len(segments)+1:03}',osm_way=w['id'],color=COLORS[wi%len(COLORS)],points=piece,mid=mid,
                            latlngs=[[lat,lon] for lon,lat in [lonlat(x0+x/256,y0+y/256,16) for x,y in piece]]))
        areas.append(dict(id=prefix,name=name,anchor_way=anchor[1],x=x0,y=y0,z=16,bounds=[[south,west],[north,east]],segments=segments))
    return areas

def main():
    raw=(OUT/'overpass.json').read_bytes()
    assert hashlib.sha256(raw).hexdigest()==json.loads((OUT/'provenance.json').read_text())['sha256']
    areas=select_areas(json.loads(raw));selection=OUT/'areas.json'
    if selection.exists():assert json.loads(selection.read_text('utf8'))==areas
    else:selection.write_text(json.dumps(areas,ensure_ascii=False,indent=2),encoding='utf8')
    cache=TileCache(default_data());font=ImageFont.truetype('C:/Windows/Fonts/arialbd.ttf',18);manifests=[]
    for area in areas:
        for source in HISTORICAL:
            original=OUT/f'{area["id"]}-{source}-original.png';tiles=[]
            im=Image.new('RGB',(1024,1024),'white')
            for dy in range(4):
                for dx in range(4):
                    p,meta,_=cache.get(source,16,area['x']+dx,area['y']+dy);tiles.append(meta)
                    with Image.open(p) as tile:im.paste(tile.convert('RGB'),(dx*256,dy*256))
            im.save(original);draw=ImageDraw.Draw(im);boxes=[]
            for s in area['segments']:
                draw.line([tuple(p) for p in s['points']],fill=s['color'],width=3)
                x,y=s['mid'];options=[]
                for radius in (0,30,60,90,120):
                    for angle in range(0,360,45):
                        cx=max(30,min(994,x+radius*math.cos(math.radians(angle))));cy=max(14,min(1010,y+radius*math.sin(math.radians(angle))));b=[cx-29,cy-13,cx+29,cy+13]
                        overlap=sum(max(0,min(b[2],c[2])-max(b[0],c[0]))*max(0,min(b[3],c[3])-max(b[1],c[1])) for c in boxes)
                        options.append((overlap*1000+radius,b,cx,cy))
                _,b,cx,cy=min(options,key=lambda v:v[0]);boxes.append(b)
                draw.line([(x,y),(cx,cy)],fill=s['color'],width=1);draw.rounded_rectangle(b,3,fill='white',outline=s['color'],width=2);draw.text((cx,cy),s['id'],anchor='mm',font=font,fill=s['color'])
            im.save(OUT/f'{area["id"]}-{source}-overlay.png')
            manifests.append(dict(area=area['id'],source=source,tiles=tiles,raw_sha256=hashlib.sha256(original.read_bytes()).hexdigest()))
            (OUT/'manifest.json').write_text(json.dumps(manifests,ensure_ascii=False,indent=2),encoding='utf8')
            print(area['name'],source,len(area['segments']),'segments',flush=True)
    board=Image.new('RGB',(1200,3*650),'#f5f3eb');d=ImageDraw.Draw(board)
    for row,a in enumerate(areas):
        d.text((12,row*650+5),f"{a['id']} / OSM anchor {a['anchor_way']} / 1916 original and OSM overlay",font=font,fill='#193b35')
        for col,kind in enumerate(('original','overlay')):
            with Image.open(OUT/f'{a["id"]}-JM50K_1916-{kind}.png') as im:board.paste(im.resize((590,590)),(col*600,row*650+40))
    board.save(OUT/'comparison.jpg',quality=92)

if __name__=='__main__':main()
