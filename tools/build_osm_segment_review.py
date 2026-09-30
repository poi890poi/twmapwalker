"""Freeze numbered OSM segments and render review overlays; no detector inputs."""
import hashlib,json,math,sys
from pathlib import Path
import numpy as np
from PIL import Image,ImageDraw,ImageFont
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from mapwalker.geo import world,lonlat
from mapwalker.osm import normalize
OUT=ROOT/'evidence/osm-segment-review'
COLORS=['#0064cf','#d12679','#007b42','#843dc2','#a75400']

def clip(a,b):
    """Float Liang–Barsky clipping; never clamp vertices into invented paths."""
    x,y=a;dx,dy=b[0]-x,b[1]-y;lo,hi=0.,1.
    for p,q in ((-dx,x),(dx,1024-x),(-dy,y),(dy,1024-y)):
        if p==0:
            if q<0:return None
        elif p<0:lo=max(lo,q/p)
        else:hi=min(hi,q/p)
    if lo>=hi:return None
    return [[x+lo*dx,y+lo*dy],[x+hi*dx,y+hi*dy]]

def clipped_runs(points):
    result=[];run=[]
    for a,b in zip(points,points[1:]):
        pair=clip(a,b)
        if pair is None:
            if len(run)>1:result.append(run)
            run=[];continue
        a,b=pair
        if run and math.dist(run[-1],a)>1e-5:
            result.append(run);run=[]
        if not run:run=[a]
        run.append(b)
    if len(run)>1:result.append(run)
    return result

def split_run(points,limit=160):
    result=[];run=[points[0]];used=0
    for end in points[1:]:
        start=run[-1];distance=math.dist(start,end)
        while distance>limit-used+1e-7:
            ratio=(limit-used)/distance
            mid=[start[i]+(end[i]-start[i])*ratio for i in (0,1)]
            run.append(mid);result.append(run);run=[mid];start=mid;used=0;distance=math.dist(start,end)
        run.append(end);used+=distance
    if len(run)>1 and used>1e-7:result.append(run)
    return result

def midpoint(points):
    lengths=[math.dist(a,b) for a,b in zip(points,points[1:])];remaining=sum(lengths)/2
    for a,b,d in zip(points,points[1:],lengths):
        if d and remaining<=d:return [a[i]+(b[i]-a[i])*remaining/d for i in (0,1)]
        remaining-=d
    return points[-1]

def main():
    raw=(OUT/'overpass.json').read_bytes();meta=json.loads((OUT/'provenance.json').read_text())
    assert hashlib.sha256(raw).hexdigest()==meta['sha256']
    features=sorted(normalize(json.loads(raw)),key=lambda f:f['properties']['osm_id']);segments=[]
    for way_index,f in enumerate(features):
        prop=f['properties'];part=0
        for line in f['geometry']['coordinates']:
            points=[[(world(lon,lat,16)[0]-54895)*256,(world(lon,lat,16)[1]-28091)*256] for lon,lat in line]
            for run in clipped_runs(points):
                for piece in split_run(run):
                    part+=1;sid=f'S{len(segments)+1:03}'
                    length=sum(math.dist(a,b) for a,b in zip(piece,piece[1:]));mid=midpoint(piece)
                    segments.append(dict(id=sid,osm_way=prop['osm_id'],part=part,name=prop['name'],highway=prop['tags']['highway'],
                        color=COLORS[way_index%len(COLORS)],url=prop['url'],points=piece,mid=mid,
                        latlngs=[[lat,lon] for lon,lat in [lonlat(54895+x/256,28091+y/256,16) for x,y in piece]],
                        length_m=round(length*156543.03392*math.cos(math.radians(24.86))/2**16)))
    doc=dict(version='wulai-osm-20260930-v1',source_sha256=meta['sha256'],segments=segments,
             bounds=[[24.85154994418473,121.5472412109375],[24.871486319357974,121.5692138671875]])
    target=OUT/'segments.json'
    if target.exists():assert json.loads(target.read_text('utf8'))==doc,'Never silently renumber an existing review set'
    else:target.write_text(json.dumps(doc,ensure_ascii=False,indent=2),encoding='utf8')
    # Readable static overview IDs use leaders; interactive page supports isolated selection.
    font=ImageFont.truetype('C:/Windows/Fonts/arialbd.ttf',16)
    for source in ('JM50K_1924_new','JM50K_1916'):
        im=Image.open(ROOT/f'evidence/trail-round4/{source}-wulai.png').convert('RGB');draw=ImageDraw.Draw(im)
        for s in segments:draw.line([tuple(p) for p in s['points']],fill=s['color'],width=3)
        occupied=[]
        for s in segments:
            x,y=s['mid'];candidates=[]
            for radius in (0,22,40,65,90,120,160):
                for angle in range(0,360,30):
                    cx=min(998,max(26,x+radius*math.cos(math.radians(angle))));cy=min(1012,max(12,y+radius*math.sin(math.radians(angle))))
                    box=[cx-25,cy-11,cx+25,cy+11]
                    overlap=sum(max(0,min(box[2],b[2])-max(box[0],b[0]))*max(0,min(box[3],b[3])-max(box[1],b[1])) for b in occupied)
                    candidates.append((overlap*1000+radius,box,cx,cy))
            _,box,cx,cy=min(candidates,key=lambda v:v[0]);occupied.append(box)
            draw.line([(x,y),(cx,cy)],fill=s['color'],width=1)
            draw.rounded_rectangle(box,radius=3,fill='white',outline=s['color'],width=2)
            draw.text((cx,cy),s['id'],font=font,fill=s['color'],anchor='mm')
        im.save(OUT/f'{source}-numbered.png')
    print(f'{len(features)} OSM ways -> {len(segments)} numbered segments')

if __name__=='__main__':main()
