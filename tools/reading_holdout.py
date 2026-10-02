"""Fresh, fixed pixel sample; freeze before viewing, score separately afterward."""
import hashlib
import json
import re
import sqlite3
import sys
from pathlib import Path

from PIL import Image,ImageDraw

ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from mapwalker.reading_suggestions import ReadingSuggestions,evidence_crop

OUT=ROOT/'evidence/reading-improvements'


def main():
    path=OUT/'holdout-inputs.json'
    if not path.exists():
        rows=json.loads((ROOT/'evidence/multi-evidence/inputs.json').read_text('utf-8'))
        used={s['id'] for s in json.loads((OUT/'inputs.json').read_text('utf-8'))}
        ordered=sorted((r for r in rows if str(r['id']) not in used),
                       key=lambda r:hashlib.sha256(f"reading-holdout-oct2-{r['id']}".encode()).hexdigest())
        numeric=[r for r in ordered if re.fullmatch(r'\d{3,4}(?:[.,]\d+)?',r['text'] or '')][:6]
        unread=[r for r in ordered if not r['text'] and max(r['box'][2]-r['box'][0],r['box'][3]-r['box'][1])<=80][:6]
        db=sqlite3.connect(f'file:{ROOT/"data/mapwalker.sqlite3"}?mode=ro',uri=True);db.row_factory=sqlite3.Row
        inputs=[]
        for selected in numeric+unread:
            r=dict(db.execute('''SELECT p.id,p.box,p.kind,t.source,t.z,t.x,t.y,j.manifest,a.spec FROM pois p
               JOIN jobs j ON p.job_id=j.id JOIN tiles t ON j.tile_id=t.id JOIN algorithms a ON a.fingerprint=j.algorithm
               WHERE p.id=?''',(selected['id'],)).fetchone())
            for key in ('box','manifest','spec'):r[key]=json.loads(r[key])
            r['selection']='baseline-numeric' if selected in numeric else 'unread-small-region';inputs.append(r)
        path.write_text(json.dumps(inputs,ensure_ascii=False,indent=2),'utf-8')
    inputs=json.loads(path.read_text('utf-8'));reader=ReadingSuggestions(ROOT/'data');output=[]
    sheet=Image.new('RGB',(1200,((len(inputs)+3)//4)*310),'white');draw=ImageDraw.Draw(sheet)
    for n,item in enumerate(inputs):
        image,box,_=evidence_crop(ROOT/'data',item,64)
        image.save(OUT/f"holdout-{item['id']}.png")
        preview=image.copy();ImageDraw.Draw(preview).rectangle(box,outline='red',width=1)
        preview.thumbnail((280,260));x=n%4*300;y=n//4*310;sheet.paste(preview,(x+10,y+30))
        draw.text((x+10,y+8),f"#{item['id']} {item['selection']}",fill='black')
        output.append(dict(id=item['id'],results={mode:reader.suggest(item,mode) for mode in ('numbers','kana')}))
    sheet.save(OUT/'holdout-contact.png')
    (OUT/'holdout-results.json').write_text(json.dumps(dict(input_sha256=hashlib.sha256(path.read_bytes()).hexdigest(),
        harness_sha256=hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),results=output),ensure_ascii=False,indent=2),'utf-8')
    print('Holdout frozen and run:',len(output))


if __name__=='__main__':main()
