"""OSM context and deliberately displaced controls; never claims OSM is truth."""
import hashlib,json,math,sqlite3,sys
from pathlib import Path
import cv2,numpy as np
from PIL import Image,ImageDraw
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from mapwalker.osm import normalize
from mapwalker.geo import world

def sample(line):
    rows=[]
    for a,b in zip(line,line[1:]):
        a=np.array(a);b=np.array(b);delta=b-a;length=np.linalg.norm(delta)
        if length<1:continue
        normal=np.array([-delta[1],delta[0]])/length
        for t in np.arange(0,length,4)/length:rows.append((a+delta*t,normal))
    return rows

def main():
    out=ROOT/'evidence/trail-round4';target=out/'osm-controls-v1.json'
    if target.exists():raise RuntimeError('Preserve prior run')
    db=sqlite3.connect((ROOT/'data/osm/context.sqlite3').as_uri()+'?mode=ro',uri=True)
    features={};sources=[]
    for (raw,) in db.execute("select raw_path from requests where state='complete' order by key"):
        p=ROOT/'data/osm'/raw;payload=p.read_bytes()
        sources.append(dict(path=raw,sha256=hashlib.sha256(payload).hexdigest()))
        for f in normalize(json.loads(payload)):
            prop=f['properties']
            if prop['osm_type']=='way' and prop['category']=='trail':features[prop['osm_id']]=f
    db.close();runs=[];retained={}
    connected=json.loads((out/'connected-v1.json').read_text())
    for scene in json.loads((out/'inputs.json').read_text())['scenes']:
        image=Image.open(out/scene['path']).convert('RGB');draw=ImageDraw.Draw(image)
        h,w=image.height,image.width;prob=np.load(out/(scene['id']+'-road-prob.npy'))
        dash=np.zeros((h,w),np.float32)
        raw=next(r for r in connected if r['scene']==scene['id'])
        for p in next(r for r in raw['runs'] if r['method']=='connected-135')['paths']:
            cv2.polylines(dash,[np.round(p['points']).astype('int32')],False,1,3)
        paths=[];samples=[]
        for oid,f in features.items():
            for line in f['geometry']['coordinates']:
                points=[[(world(lon,lat,scene['z'])[0]-scene['x'])*256,(world(lon,lat,scene['z'])[1]-scene['y'])*256] for lon,lat in line]
                if not any(cv2.clipLine((0,0,w,h),tuple(np.round(a).astype(int)),tuple(np.round(b).astype(int)))[0] for a,b in zip(points,points[1:])):continue
                retained[oid]=f
                draw.line([tuple(p) for p in points],fill='#008ebf',width=4)
                paths.append(dict(osm_id=oid,name=f['properties']['name'],points=points))
                # Exactly the same route samples for all shifts and cross sections.
                for p,n in sample(points):
                    if 191<=p[0]<w-191 and 41<=p[1]<h-41:samples.append((p,n))
        image.save(out/(scene['id']+'-osm.png'))
        controls=[]
        for shift in (0,-150,150):
            scores=[];dash_scores=[]
            for p,n in samples:
                coords=np.rint(p+np.array([shift,0])+np.arange(-40,41)[:,None]*n).astype(int)
                scores.append(float(prob[coords[:,1],coords[:,0]].max()))
                dash_scores.append(float(dash[coords[:,1],coords[:,0]].max()))
            controls.append(dict(shift_x_px=shift,samples=len(scores),road_supported_fraction=float(np.mean(np.array(scores)>=.5)) if scores else None,
                connected_dash_supported_fraction=float(np.mean(dash_scores)) if scores else None,
                mean_cross_section_max=float(np.mean(scores)) if scores else None))
        runs.append(dict(scene=scene['id'],osm_paths=paths,controls=controls))
    target.write_text(json.dumps(dict(attribution='© OpenStreetMap contributors, ODbL 1.0',sources=sources,runs=runs),ensure_ascii=False,indent=2),encoding='utf8')
    (out/'osm-trails.geojson').write_text(json.dumps(dict(type='FeatureCollection',features=list(retained.values())),ensure_ascii=False),encoding='utf8')
    for r in runs:print(r['scene'],r['controls'])

if __name__=='__main__':main()
