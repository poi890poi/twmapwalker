"""Post-run comparison with user annotations. Never imported by inference."""
import hashlib
import html
import json
import math
import sqlite3
import sys
import time
from pathlib import Path

from PIL import Image, ImageDraw

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from mapwalker.geo import world
from mapwalker.paths import default_data
from mapwalker.sources import TileCache


def main():
    folder = ROOT / 'evidence' / 'user-review'
    reference = json.loads((folder / 'reference-before.json').read_text('utf-8'))
    center = world(*reference['map_geometry']['center'], 16)
    origin = [center[0]*256-822.5*2, center[1]*256-399*2]
    db = sqlite3.connect(default_data() / 'mapwalker.sqlite3')
    db.row_factory = sqlite3.Row
    rows = [dict(r) for r in db.execute('''SELECT p.*,t.x,t.y,t.z,a.name algorithm,j.algorithm fingerprint
        FROM pois p JOIN jobs j ON p.job_id=j.id JOIN tiles t ON j.tile_id=t.id
        JOIN algorithms a ON j.algorithm=a.fingerprint
        WHERE a.active=1 AND j.state='complete' AND t.source='JM50K_1924_new' ''')]
    for p in rows:
        p['box'] = json.loads(p['box'])
        p['details'] = json.loads(p['details'])
        p['screen_box'] = [(p['x']*256+p['box'][i]-origin[0])/2 if i%2==0
                           else (p['y']*256+p['box'][i]-origin[1])/2 for i in range(4)]
    cache = TileCache(default_data())
    manifests = {}

    def crop(box):
        left, top, right, bottom = [int(round(v*2+origin[i%2])) for i,v in enumerate(box)]
        image = Image.new('RGB', (right-left, bottom-top), 'white')
        for y in range(math.floor(top/256), math.ceil(bottom/256)):
            for x in range(math.floor(left/256), math.ceil(right/256)):
                path, meta, _ = cache.get('JM50K_1924_new',16,x,y)
                manifests[f'{x}/{y}'] = meta
                with Image.open(path) as tile:
                    image.paste(tile.convert('RGB'), (x*256-left,y*256-top))
        return image

    results = []
    cards = []
    for ref in reference['landmarks']:
        box = ref['screen_box']
        candidates = []
        for p in rows:
            b = p['screen_box']
            cx,cy = (b[0]+b[2])/2, (b[1]+b[3])/2
            if box[0] <= cx <= box[2] and box[1] <= cy <= box[3]:
                candidates.append(p)
        jobs = [dict(r) for r in db.execute('''SELECT j.state,a.name,j.algorithm,j.telemetry,j.manifest
            FROM jobs j JOIN tiles t ON j.tile_id=t.id JOIN algorithms a ON j.algorithm=a.fingerprint
            WHERE a.active=1 AND t.source='JM50K_1924_new' AND t.x=? AND t.y=?''',(ref['x'],ref['y']))]
        expanded = [box[0]-12,box[1]-12,box[2]+12,box[3]+12]
        clean = crop(expanded)
        clean.save(folder / (ref['id']+'-source.png'))
        overlay = clean.copy()
        draw = ImageDraw.Draw(overlay)
        for p in candidates:
            b = p['screen_box']
            draw.rectangle([(b[i]-expanded[i%2])*2 for i in range(4)],
                           outline='#be7b08' if p['kind']=='text' else '#007e73', width=2)
        overlay.save(folder / (ref['id']+'-proposals.png'))
        texts = [p for p in candidates if p['kind']=='text']
        raw = ', '.join(f'{p["text"]} ({p["algorithm"]}, {p["disposition"]})' for p in texts) or 'No text proposal'
        shapes = sum(p['kind']!='text' for p in candidates)
        results.append(dict(reference=ref,after_jobs=jobs,center_in_reference_proposals=candidates))
        cards.append(f'''<article><h2>{html.escape(ref['id'])}</h2>
          <div class="images"><figure><img src="{ref['id']}-source.png"><figcaption>Original pixels</figcaption></figure>
          <figure><img src="{ref['id']}-proposals.png"><figcaption>Returned proposals</figcaption></figure></div>
          <p>Before: {len(ref['before_jobs'])} recorded runs. After: {sum(j['state']=='complete' for j in jobs)}/{len(jobs)} complete.</p>
          <p><strong>{html.escape(raw)}</strong></p><p>{shapes} nearby shape/trail proposals. These are not proof that the character or landmark was found.</p></article>''')
    context = crop([655,190,935,425]); context.save(folder/'label-context.png')
    algorithms = [dict(r) for r in db.execute('SELECT * FROM algorithms WHERE active=1')]
    telemetry = [dict(r) for r in db.execute('''SELECT t.source,t.z,t.x,t.y,a.name,j.state,j.telemetry,j.manifest
        FROM jobs j JOIN tiles t ON j.tile_id=t.id JOIN algorithms a ON j.algorithm=a.fingerprint WHERE a.active=1''')]
    payload = dict(created_at=time.time(), reference_sha256=hashlib.sha256((folder/'reference-before.json').read_bytes()).hexdigest(),
                   selection_rule='Proposal center inside the user-drawn screen box; spatial association only, not accuracy',
                   algorithms=algorithms,results=results,inputs=list(manifests.values()),runs=telemetry,
                   decision='Coverage completed; OCR misses and incomplete trail geometry remain unresolved. No recognition-quality claim.')
    (folder/'result-after.json').write_text(json.dumps(payload,ensure_ascii=False,indent=2),'utf-8')
    report = '''<!doctype html><html lang="en"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
    <title>Marked landmarks · Mapwalker evidence</title><style>
    body{max-width:1120px;margin:40px auto;padding:0 24px;background:#f7f6ef;color:#173b36;font:16px/1.6 system-ui}
    h1{font:42px Georgia}h2{font-size:20px}a{color:#186456}article{background:white;padding:22px;border:1px solid #d8dfd5;border-radius:12px}
    .grid{display:grid;grid-template-columns:1fr 1fr;gap:20px}.images{display:flex;gap:16px;align-items:start}figure{margin:0;flex:1}img{max-width:100%}figcaption{font-size:13px;color:#68776d}
    .notice{padding:18px;background:#f3e7c8;border-left:4px solid #b98721;margin:24px 0}.context{max-width:560px;display:block} @media(max-width:700px){.grid{grid-template-columns:1fr}}
    </style><a href="../report.html">← Evidence notebook</a><h1>Your marked landmarks</h1>
    <p>The eight circled targets were on tiles without recorded processing in the original screenshot.
    The full shown view has now completed all five algorithms: 56 native tiles per historical layer,
    112 tiles and 560 runs across both layers. The earlier sample report remains frozen separately.</p>
    <div class="notice"><strong>Coverage is not detection quality.</strong> The elevation 651 and individual 後 and 桶 characters are now returned.
    ウライ社 and the circled 溪 still have no text output. The complete name 桶後溪 is not assembled or verified.
    Shape boxes on stroke fragments do not count as successful landmark recognition.</div>
    <p>Orange boxes are text proposals; teal boxes are nearby shape/trail proposals. Selection uses a proposal's center inside each user circle,
    and may include unrelated contour fragments. No precision or recall is inferred from these counts.
    Original pixels below are at native zoom 16. User markings and supplied readings were used only after inference.</p>
    <img class="context" src="label-context.png" alt="Original vertical and river labels at native resolution"><p>Original label context (no supplied names inserted).</p>
    <div class="grid">'''+''.join(cards)+'''</div><h2>The three marked paths</h2>
    <p>The drawn paths are preserved in the independent reference. Their trail/stream interpretation is not yet confirmed.
    The existing detector returns disconnected dash chains; it does not reconstruct the complete drawn routes.
    This is an unresolved gap, not a successful path match.</p>
    <p><a href="marked-landmarks.jpg">Your original annotation</a> · <a href="reference-before.json">Frozen before-state</a> ·
    <a href="result-after.json">After-state, hashes, raw proposals and run telemetry</a></p></html>'''
    (folder/'report.html').write_text(report,'utf-8')
    for r in results:
        print(r['reference']['id'],[(p['kind'],p['text']) for p in r['center_in_reference_proposals']])


if __name__=='__main__':
    sys.stdout.reconfigure(encoding='utf-8')
    main()
