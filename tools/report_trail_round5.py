"""Publish saved outputs; no tuning or inference during report generation."""
import hashlib,json,statistics
from pathlib import Path
from PIL import Image,ImageDraw,ImageFont
ROOT=Path(__file__).resolve().parents[1];OUT=ROOT/'evidence/trail-round5'

def main():
    names=[f'{a}-{s}' for a in ('J','N','H','fresh-J') for s in ('JM50K_1924_new','JM50K_1916')]
    rows=[]
    for name in names:
        row=json.loads((OUT/f'{name}.json').read_text('utf8'));worn=OUT/'worn'/f'{name}.json'
        if worn.exists():
            v=json.loads(worn.read_text('utf8'));row['worn']=dict(paths=len(v['paths']),dense_pixels=v['dense_pixels'],inference_s=v['inference_s'])
        row['path_count']=len(row['paths']);row['baseline_count']=len(row['baseline_paths'])
        row['longest_path_px']=max([p['length_px'] for p in row['paths']],default=0)
        row['total_path_px']=sum(p['length_px'] for p in row['paths'])
        row['guided_count']=len(row['variants'][0]['paths']);row['shift_control_count']=len(row['variants'][1]['paths'])
        source=OUT/f'{name}-input.png' if name.startswith('fresh-') else ROOT/'evidence/trail-area-comparison'/f'{name}-original.png'
        assert hashlib.sha256(source.read_bytes()).hexdigest()==row['input_sha256']
        # Different Pillow builds can encode identical pixels into different PNG bytes.
        with Image.open(source) as a,Image.open(OUT/f'{name}-original.png') as b:
            assert a.convert('RGB').tobytes()==b.convert('RGB').tobytes()
        row['display_sha256']=hashlib.sha256((OUT/f'{name}-original.png').read_bytes()).hexdigest()
        rows.append(row)
    times=[r['inference_s'] for r in rows]
    doc=dict(scenes=rows,likelihood_seconds=dict(min=min(times),median=statistics.median(times),max=max(times)),note='Counts and lengths are output amounts, not recall or accuracy. Synthetic validation is separate from real-map evaluation.')
    (OUT/'report.json').write_text(json.dumps(doc,ensure_ascii=False,indent=2),encoding='utf8')
    font=ImageFont.truetype('C:/Windows/Fonts/arial.ttf',22)
    board=Image.new('RGB',(1536,568),'#f5f3eb');draw=ImageDraw.Draw(board)
    for i,(kind,title) in enumerate([('original','Original historical map'),('baseline','Previous dash graph'),('connected','New image-only candidate')]):
        draw.text((i*512+12,10),title,font=font,fill='#193b35')
        with Image.open(OUT/f'J-JM50K_1924_new-{kind}.png') as im:board.paste(im.resize((512,512)),(i*512,45))
    board.save(OUT/'comparison.jpg',quality=94)
    # Keep model weights small and review-reproducible; no third-party artifacts.
    for suffix in ('','worn/'):
        p=OUT/suffix;p.mkdir(exist_ok=True)
        (p/'dashnet.pt').write_bytes((ROOT/'data/trail-round5'/suffix/'dashnet.pt').read_bytes())
    for name in ('synthetic_dash_model.py','synthetic_dash_worn.py','train_synthetic_dash.py','run_trail_round5.py','fetch_trail_round5_holdout.py','report_trail_round5.py'):
        (OUT/('frozen-'+name)).write_bytes((ROOT/'tools'/name).read_bytes())
    print(json.dumps({r['id']:[r['baseline_count'],r['path_count'],r['guided_count'],r['shift_control_count']] for r in rows}),flush=True)

if __name__=='__main__':main()
