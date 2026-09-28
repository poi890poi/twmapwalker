"""Freeze unannotated discovery inputs separately from recognition-only references."""
import hashlib,json,sys
from pathlib import Path
from PIL import Image
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from mapwalker.sources import TileCache
from mapwalker.paths import default_data
OUT=ROOT/'evidence/model-trials';(OUT/'inputs').mkdir(exist_ok=True)
if (OUT/'inputs.json').exists(): raise RuntimeError('Frozen inputs already exist')
cache=TileCache(default_data());scenes=[]
points=[('vertical',54896,28092),('river',54897,28093),('elevation',54900,28092),('skewed',54895,28091),('symbols',54895,28092)]
for source in ['JM50K_1924_new','JM50K_1916']:
 for name,x,y in points+[('holdout-west',54892,28087),('holdout-east',54902,28088)]:
  if source=='JM50K_1916' and name not in ['vertical','symbols','holdout-west','holdout-east']: continue
  im,manifest,timing=cache.mosaic(source,16,x,y)
  name=f'{source}-{name}';path=OUT/'inputs'/f'{name}.png';im.save(path)
  scenes.append(dict(id=name,path='inputs/'+path.name,source=source,z=16,x=x,y=y,split='holdout' if 'holdout' in name else 'development',sha256=hashlib.sha256(path.read_bytes()).hexdigest(),manifest=manifest))
  print(name,flush=True)
crops=[]
labels=['ウ','ラ','イ','社','溪','後','桶','651']
refs=json.loads((ROOT/'evidence/user-review/reference-before.json').read_text('utf-8'))['landmarks']
for ref,expected in zip(refs,labels):
 im=Image.open(ROOT/'evidence/user-review'/f'{ref["id"]}-source.png')
 path=OUT/'inputs'/f'crop-{ref["id"]}.png';im.save(path)
 crops.append(dict(id=ref['id'],path='inputs/'+path.name,expected=expected,role='recognition-only oracle crop; not discovery',sha256=hashlib.sha256(path.read_bytes()).hexdigest()))
context=Image.open(ROOT/'evidence/user-review/label-context.png')
for name,im,expected in [('vertical-word',context.crop((20,30,140,345)),'ウライ社'),('river-word',context.crop((125,190,545,465)),'桶後溪'),('contour-negative',context.crop((340,5,555,180)),''),('blank-negative',Image.new('RGB',(180,100),'white'),'')]:
 path=OUT/'inputs'/f'crop-{name}.png';im.save(path)
 crops.append(dict(id=name,path='inputs/'+path.name,expected=expected,role='recognition-only oracle crop; not discovery',sha256=hashlib.sha256(path.read_bytes()).hexdigest()))
(OUT/'inputs.json').write_text(json.dumps(dict(angles=[0,-45,45,90,180,270],discovery=scenes,recognition=crops),ensure_ascii=False,indent=2),'utf-8')
