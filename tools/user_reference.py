"""Georeference user-drawn review marks; never consumed by the runtime detectors."""
import hashlib
import json
import shutil
import sys
import urllib.request
from pathlib import Path

import numpy as np
from PIL import Image

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from mapwalker.geo import world,lonlat

folder=ROOT/'evidence'/'user-review'
pristine=folder/'pristine-map.png'
if not pristine.exists():
    shutil.copyfile(ROOT/'evidence'/'ui-map.png',pristine)
user=Image.open(folder/'marked-landmarks.jpg').convert('RGB')
base=Image.open(pristine).convert('RGB')
a=np.asarray(user).astype(float);b=np.asarray(base).astype(float)
red=(a[:,:,0]>180)&(a[:,:,0]>a[:,:,1]*1.4)&(a[:,:,0]>a[:,:,2]*1.4)
mae=float(np.abs(a-b)[~red].mean())
if user.size!=(1280,720) or base.size!=user.size or mae>6:
    raise ValueError('Screenshot geometry could not be verified; do not use guessed georeferencing')
center=np.array(world(121.559,24.859,15))*256
def coord(px,py):
    p=center+np.array([px-822.5,py-399])
    return lonlat(p[0]/256,p[1]/256,15)

boxes=[('vertical-label-1',[671,211,718,248]),('vertical-label-2',[682,248,717,278]),
       ('vertical-label-3',[682,278,715,317]),('vertical-label-4',[680,315,713,354]),
       ('river-label-1',[725,291,780,337]),('river-label-2',[792,335,838,375]),
       ('river-label-3',[868,370,915,410]),('elevation',[1235,295,1279,343])]
jobs=json.load(urllib.request.urlopen('http://127.0.0.1:8765/api/jobs?limit=500'))
rows=[]
for name,box in boxes:
    lon,lat=coord((box[0]+box[2])/2,(box[1]+box[3])/2);x,y=map(int,world(lon,lat,16))
    before=[j for j in jobs if j['source']=='JM50K_1924_new' and j['x']==x and j['y']==y]
    rows.append(dict(id=name,screen_box=box,lon=lon,lat=lat,z=16,x=x,y=y,before_jobs=before,
                     west_south=coord(box[0],box[3]),east_north=coord(box[2],box[1])))
    print(name,x,y,[(j['name'],j['state']) for j in before])
paths={
 'west':[[579,307],[567,329],[585,367],[585,417],[558,451],[531,464],[497,477],[463,498],[416,515],[372,539]],
 'east-inner':[[699,348],[708,355],[726,397],[744,425],[788,450],[841,464],[861,487],[864,521],[901,544],[925,549],[938,561],[931,597],[930,617]],
 'east-outer':[[724,344],[765,364],[790,385],[821,399],[847,420],[874,432],[895,448],[927,459],[945,484],[964,501],[999,515],[1005,555],[1000,590],[1013,603],[1039,618]]}
payload=dict(provenance='User-marked independent reference; never a detector input',
             image_sha256=hashlib.sha256((folder/'marked-landmarks.jpg').read_bytes()).hexdigest(),
             pristine_sha256=hashlib.sha256(pristine.read_bytes()).hexdigest(),image_comparison_non_red_mae=mae,
             map_geometry=dict(zoom=15,center=[121.559,24.859],map_rect=[365,78,915,642]),landmarks=rows,
             paths=[dict(id=name,semantic_type='awaiting user clarification',screen_points=points,
                         coordinates=[coord(*p) for p in points]) for name,points in paths.items()],
             viewport=[*coord(365,720),*coord(1280,78)])
target=folder/'reference-before.json'
if target.exists():
    raise ValueError('Before-state reference already exists; preserve it instead of overwriting')
target.write_text(json.dumps(payload,indent=2),'utf-8')
print('Viewport',payload['viewport'],'non-red screenshot MAE',mae)
