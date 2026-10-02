"""Freeze and render newly surfaced hypotheses before visual assessment."""
import json
import sys
from pathlib import Path

from PIL import Image,ImageDraw

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from tools.probe_hollow_dots import crop_cached


def main():
    out=ROOT/'evidence/multi-evidence'
    result=json.loads((out/'evaluation.json').read_text('utf-8'))
    rows={r['id']:r for r in json.loads((out/'inputs.json').read_text('utf-8'))}
    selected=[s for s in result['samples'] if s['result']['state']!='unknown']
    labels=json.loads((out/'evaluation-labels.json').read_text('utf-8'))
    manifest=[];sheet=Image.new('RGB',(1200,((len(selected)+3)//4)*310),'#f4f3ea');draw=ImageDraw.Draw(sheet)
    for i,s in enumerate(selected):
        pid=s['id'];image,box,provenance=crop_cached(rows[pid]);image.save(out/f'{pid}.png')
        image=image.resize((250,250));x=(i%4)*300+10;y=(i//4)*310+35
        sheet.paste(image,(x,y));draw.text((x,y-27),f"#{pid} {s['result']['state']}",fill='black')
        manifest.append(dict(id=pid,previously_annotated=str(pid) in labels,provenance=provenance,
                             crop_box=box,visual_assessment='pending'))
    (out/'visual-sample.json').write_text(json.dumps(manifest,indent=2),'utf-8')
    sheet.save(out/'hypotheses.jpg')


if __name__=='__main__':main()
