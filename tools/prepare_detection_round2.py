"""Freeze pixels only. References live separately and never enter inference."""
import json,hashlib,sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from mapwalker.sources import TileCache
from mapwalker.paths import default_data
OUT=ROOT/'evidence/detection-round2'
def main():
 if (OUT/'inputs.json').exists():raise RuntimeError('Inputs already frozen')
 (OUT/'inputs').mkdir(parents=True,exist_ok=True)
 old=json.loads((ROOT/'evidence/symbol-first/inputs.json').read_text('utf-8'))
 scenes=[{**s,'path':'../symbol-first/'+s['path'],'split':'development'} for s in old['scenes']]
 cache=TileCache(default_data())
 for source in ['JM50K_1924_new','JM50K_1916']:
  for label,x,y in [('fresh-southwest',54894,28094),('fresh-southeast',54899,28094)]:
   im,manifest,timing=cache.mosaic(source,16,x,y)
   name=f'{source}-{label}';path=OUT/'inputs'/f'{name}.png';im.save(path)
   scenes.append(dict(id=name,path='inputs/'+path.name,source=source,z=16,x=x,y=y,split='fresh',sha256=hashlib.sha256(path.read_bytes()).hexdigest(),manifest=manifest))
 (OUT/'inputs.json').write_text(json.dumps(dict(angles=old['angles'],scenes=scenes),ensure_ascii=False,indent=2),'utf-8')
 print('Frozen',len(scenes),'scenes')
if __name__=='__main__':main()
