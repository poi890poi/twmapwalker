"""Score reserved pixels before visual labels; no fitting or threshold updates."""
import json
import math
from PIL import Image,ImageDraw
from .contour_frequency_trial import ROOT,OUT,SAMPLES,PARAMETERS,sha,spectrum


def main():
    target=OUT/'reserved'
    target.mkdir(exist_ok=False)
    rows=[r for r in json.loads((SAMPLES/'dataset.json').read_text(encoding='utf8')) if r['split']=='reserved-evaluation']
    result=[]
    for r in rows:
        features={}
        for name in ('mark','context'):
            p=SAMPLES/r[name];assert sha(p)==r[name+'_sha256']
            with Image.open(p) as im:features[name]=spectrum(im)
        scores={k:v.get('score',0) for k,v in features.items()};scores['joint']=min(scores.values())
        result.append(dict(id=r['id'],index=r['index'],scores=scores,rejected={k:v>=1 for k,v in scores.items()},features=features))
    # Predictions saved before any reserved contact sheet exists.
    (target/'predictions.json').write_text(json.dumps(result,indent=2)+'\n',encoding='utf8')
    (target/'lock.json').write_text(json.dumps(dict(parameters=PARAMETERS,
        trial_code_sha256=sha(ROOT/'tools/contour_frequency_trial.py'),
        dataset_sha256=sha(SAMPLES/'dataset.json'),
        predictions_sha256=sha(target/'predictions.json')),indent=2)+'\n',encoding='utf8')
    for start in range(0,len(rows),12):
        batch=rows[start:start+12]
        board=Image.new('RGB',(1200,320*math.ceil(len(batch)/4)),'white');draw=ImageDraw.Draw(board)
        for i,r in enumerate(batch):
            x=i%4*300;y=i//4*320
            with Image.open(SAMPLES/r['context']) as image:im=image.copy()
            ImageDraw.Draw(im).rectangle(r['context_box'],outline='red',width=1)
            board.paste(im.resize((288,288),Image.Resampling.NEAREST),(x+6,y+29))
            draw.text((x+6,y+3),f"{r['index']}  POI {r['id']}  {r['source']}",fill='black')
        board.save(target/f'sheet-{start//12}.jpg',quality=94)
    print(f'Scored {len(rows)} reserved crops before visual labelling. Thresholds unchanged.')


if __name__=='__main__':main()
