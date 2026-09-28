"""Freeze symbol-first inputs; annotation is a separate post-run evaluation file."""
import sys,json,hashlib
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from mapwalker.sources import TileCache
from mapwalker.paths import default_data
OUT=ROOT/'evidence/symbol-first';(OUT/'inputs').mkdir(parents=True,exist_ok=True)
if (OUT/'inputs.json').exists():raise RuntimeError('Inputs already frozen')
old=json.loads((ROOT/'evidence/model-trials/inputs.json').read_text('utf-8'))
scenes=[{**s,'path':'../model-trials/'+s['path'],'split':'previous-'+s['split']} for s in old['discovery']]
cache=TileCache(default_data())
for source in ['JM50K_1924_new','JM50K_1916']:
 for label,x,y in [('new-north',54898,28090),('new-west',54892,28095)]:
  im,manifest,timing=cache.mosaic(source,16,x,y)
  name=f'{source}-{label}';path=OUT/'inputs'/f'{name}.png';im.save(path)
  scenes.append(dict(id=name,path='inputs/'+path.name,source=source,z=16,x=x,y=y,split='fresh-unannotated',sha256=hashlib.sha256(path.read_bytes()).hexdigest(),manifest=manifest))
(OUT/'inputs.json').write_text(json.dumps(dict(angles=old['angles'],scenes=scenes),ensure_ascii=False,indent=2),'utf-8')
print('Frozen',len(scenes),'scenes')
