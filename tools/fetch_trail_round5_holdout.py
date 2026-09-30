"""One non-overlapping eastern neighbor, chosen before fetching pixels."""
import hashlib,json,sys
from pathlib import Path
from PIL import Image
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from mapwalker.paths import default_data
from mapwalker.sources import TileCache,HISTORICAL
from tools.build_trail_area_comparison import pixel_lines
from tools.build_osm_segment_review import clipped_runs
OUT=ROOT/'evidence/trail-round5';SOURCE=ROOT/'evidence/trail-area-comparison'

def main():
    area=next(a for a in json.loads((SOURCE/'areas.json').read_text('utf8')) if a['id']=='J')
    x0,y0=area['x']+4,area['y'];segments=[]
    for way in json.loads((SOURCE/'overpass.json').read_bytes())['elements']:
        if way.get('tags',{}).get('name')!='浸水營古道' or way['tags'].get('highway') not in ('path','footway','track'):continue
        for line in pixel_lines(way):
            for run in clipped_runs([[x-x0*256,y-y0*256] for x,y in line]):segments.append(dict(osm_way=way['id'],points=run))
    scope=dict(x=x0,y=y0,z=16,choice='Four tiles east of frozen Jinshuiying window, same y; no overlapping tiles',segments=segments)
    target=OUT/'holdout-scope.json'
    if target.exists():assert json.loads(target.read_text('utf8'))==scope
    else:target.write_text(json.dumps(scope,ensure_ascii=False,indent=2),encoding='utf8')
    cache=TileCache(default_data());scenes=[]
    for source in HISTORICAL:
        im=Image.new('RGB',(1024,1024));tiles=[]
        for dy in range(4):
            for dx in range(4):
                path,meta,_=cache.get(source,16,x0+dx,y0+dy);tiles.append(meta)
                with Image.open(path) as tile:im.paste(tile.convert('RGB'),(dx*256,dy*256))
        path=OUT/f'fresh-J-{source}-input.png';im.save(path)
        scenes.append(dict(id=f'fresh-J-{source}',label='浸水營 · new eastern window',source=source,path=str(path),segments=segments,tiles=tiles,sha256=hashlib.sha256(path.read_bytes()).hexdigest()))
        print(source,'new window',x0,y0,len(segments),'OSM runs',flush=True)
    (OUT/'holdout-inputs.json').write_text(json.dumps(scenes,ensure_ascii=False,indent=2),encoding='utf8')

if __name__=='__main__':main()
