"""Exact named hiking relation, including every member way; no proximity inference."""
import hashlib,json,math,sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from mapwalker.osm import lines
from mapwalker.geo import world,lonlat
from tools.build_osm_segment_review import split_run,midpoint,COLORS
OUT=ROOT/'evidence/batongguan-review'

def build(payload,members):
    relation=next(e for e in payload['elements'] if e['type']=='relation' and e['id']==13678191)
    ways={e['id']:e for e in members['elements'] if e['type']=='way'}
    required={m['ref'] for m in relation['members'] if m['type']=='way'}
    assert required<=ways.keys(),f'Missing members: {required-ways.keys()}'
    segments=[];seen=set();allpoints=[]
    for index,member in enumerate(relation['members']):
        if member['type']!='way':raise ValueError('Unexpected member type; resolve explicitly')
        oid=member['ref']
        if oid in seen:continue
        seen.add(oid);way=ways[oid];tags=way.get('tags',{});part=0
        for line in lines(way.get('geometry',[])):
            pixels=[[x*256,y*256] for x,y in [world(lon,lat,16) for lon,lat in line]]
            for piece in split_run(pixels,180):
                part+=1;mid=midpoint(piece);mlon,mlat=lonlat(mid[0]/256,mid[1]/256,16)
                coords=[[lat,lon] for lon,lat in [lonlat(x/256,y/256,16) for x,y in piece]]
                metres=sum(math.dist(a,b) for a,b in zip(piece,piece[1:]))*156543.03392*math.cos(math.radians(mlat))/2**16
                if metres<.01:continue
                sid=f'B{len(segments)+1:03}'
                segments.append(dict(id=sid,osm_way=oid,part=part,name=tags.get('name','八通關古道（路線成員）'),
                    highway=tags.get('highway',tags.get('disused:highway','unspecified')),color=COLORS[index%len(COLORS)],
                    url=f'https://www.openstreetmap.org/way/{oid}',latlngs=coords,mid_latlng=[mlat,mlon],length_m=round(metres),tags=tags,
                    route_id=13678191,member_index=index,member_role=member.get('role','')))
                allpoints.extend(coords)
    lats,lons=zip(*allpoints)
    return dict(version='batongguan-osm-20260930-v1',route=dict(id=13678191,name=relation['tags']['name'],url='https://www.openstreetmap.org/relation/13678191',members=len(required)),
        segments=segments,bounds=[[min(lats),min(lons)],[max(lats),max(lons)]],default_segment=min(segments,key=lambda s:math.dist(s['mid_latlng'],[23.55,120.94]))['id'])

def main():
    payloads=[]
    for name,meta in [('overpass.json','provenance.json'),('route-members.json','route-members-provenance.json')]:
        raw=(OUT/name).read_bytes();assert hashlib.sha256(raw).hexdigest()==json.loads((OUT/meta).read_text('utf8'))['sha256'];payloads.append(json.loads(raw))
    data=build(*payloads);target=OUT/'segments.json'
    if target.exists():assert json.loads(target.read_text('utf8'))==data,'Preserve already assigned IDs'
    else:target.write_text(json.dumps(data,ensure_ascii=False,indent=2),encoding='utf8')
    print('Members:',data['route']['members'],'Segments:',len(data['segments']),'Default:',data['default_segment'],'Bounds:',data['bounds'])

if __name__=='__main__':main()
