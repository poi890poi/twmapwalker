"""Render immutable experiment outputs; independent references are scoring only."""
import hashlib,json,statistics,sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from PIL import Image,ImageDraw,ImageFont
from mapwalker.display import priority
from mapwalker.region_model import iou
OUT=ROOT/'evidence/detection-round3'
FONT=ImageFont.truetype('C:/Windows/Fonts/arial.ttf',20)
SMALL=ImageFont.truetype('C:/Windows/Fonts/arial.ttf',16)

def rows(path):return {r['scene']:r for r in map(json.loads,path.read_text('utf-8').splitlines())}
def adapted(row):
    return [{**p,'score':min(1,p['score']),'details':{**p['details'],'profile':'synthetic-map-v1','raw_peak':p['score']}} for p in row['proposals'] if p['score']>=.95]
def score(pred,refs):
    marks=[dict(**r,iou=max((iou(p['box'],r['box']) for p in pred.get(r['scene'],[])),default=0)) for r in refs['marks']]
    negatives=[]
    for r in refs.get('negative_regions',[]):
        a,b,c,d=r['box']
        negatives.append(dict(**r,count=sum(a<=(p['box'][0]+p['box'][2])/2<c and b<=(p['box'][1]+p['box'][3])/2<d for p in pred.get(r['scene'],[]))))
    return dict(hits=sum(r['iou']>=.25 for r in marks),references=len(marks),marks=marks,background_proposals=sum(r['count'] for r in negatives),negative_regions=negatives,counts={k:len(v) for k,v in pred.items()},median_proposals=statistics.median(map(len,pred.values())))

def main():
    suites={}
    for split,manifest,reference,baseline in [
        ('development',ROOT/'evidence/symbol-first/inputs.json',ROOT/'evidence/symbol-first/references.json',ROOT/'evidence/detection-round2/craft-compact-development.jsonl'),
        ('fresh',OUT/'fresh-inputs.json',OUT/'fresh-references.json',OUT/'original-fresh.jsonl'),
        ('final',OUT/'final-inputs.json',OUT/'final-references.json',OUT/'original-final.jsonl')]:
        suffix='dev' if split=='development' else split
        old=rows(baseline);new=rows(OUT/f'consensus-{suffix}.jsonl');refs=json.loads(reference.read_text('utf-8'))
        oa={k:v['proposals'] for k,v in old.items()};na={k:adapted(v) for k,v in new.items()}
        op={k:[p for p in v if priority(p)>=.74] for k,v in oa.items()};np={k:[p for p in v if priority(p)>=.74] for k,v in na.items()}
        scenes=[]
        for s in json.loads(manifest.read_text('utf-8'))['scenes']:
            path=(manifest.parent/s['path']).resolve();assert hashlib.sha256(path.read_bytes()).hexdigest()==s['sha256']
            # Evidence references original frozen bytes without copying historic inputs.
            import os
            scenes.append({**{k:v for k,v in s.items() if k!='manifest'},'path':os.path.relpath(path,OUT).replace('\\','/')})
        suites[split]=dict(scenes=scenes,old_all=oa,new_all=na,old_eligible=op,new_eligible=np,
            metrics={name:score(pred,refs) for name,pred in [('old_all',oa),('old_eligible',op),('new_all',na),('new_eligible',np)]})
    (OUT/'review-data.json').write_text(json.dumps(suites,ensure_ascii=False),'utf-8')
    (OUT/'summary.json').write_text(json.dumps({k:v['metrics'] for k,v in suites.items()},ensure_ascii=False,indent=2),'utf-8')
    cases=[('development','JM50K_1924_new-vertical','wulai-comparison.png'),('development','JM50K_1924_new-symbols','symbols-comparison.png'),('fresh','JM50K_1924_new-west','fresh-label-comparison.png'),('final','JM50K_1916-southeast','contours-comparison.png'),('final','JM50K_1924_new-southwest','regression-comparison.png')]
    for split,sid,name in cases:
        data=suites[split];s=next(s for s in data['scenes'] if s['id']==sid);im=Image.open(OUT/s['path']).convert('RGB')
        sheet=Image.new('RGB',(1048,594),'#f4f3ea');draw=ImageDraw.Draw(sheet)
        for i,(allkey,eligiblekey,title,color) in enumerate([('old_all','old_eligible','Previous text-region detector','#225dad'),('new_all','new_eligible','Adapted detector + rotation support','#007b63')]):
            panel=im.resize((512,512));pd=ImageDraw.Draw(panel);allp=data[allkey][sid];eligible=data[eligiblekey][sid]
            for p in sorted(allp,key=lambda p:priority(p)):
                high=priority(p)>=.74;b=[v*512/384 for v in p['box']]
                pd.rectangle(b,outline=color if high else '#c58b27',width=3 if high else 1)
            x=8+i*524;sheet.paste(panel,(x,68));draw.text((x,6),title,font=FONT,fill='#193e36')
            draw.text((x,34),f'{len(allp)} retained; {len(eligible)} eligible before density limits',font=SMALL,fill='#36544d')
        sheet.save(OUT/name)
    print(json.dumps({k:{n:(m['hits'],m['references'],m['background_proposals']) for n,m in v['metrics'].items()} for k,v in suites.items()}))
if __name__=='__main__':main()
