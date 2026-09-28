"""Render raw model trials without promoting proposals to ground truth."""
import json,html,statistics,unicodedata,sys
from pathlib import Path
import numpy as np
from PIL import Image
ROOT=Path(__file__).resolve().parents[1];OUT=ROOT/'evidence/model-trials'
MODELS=['baseline','ppocr6','craft','manga','dino','yolo']
def esc(x):return html.escape(str(x))
def readings(raw):
 if isinstance(raw,str):return raw
 return ' | '.join(f'{x[0] or chr(8709)} ({float(x[1]):.2f})' for x in raw or [])
def main():
 suite=json.loads((OUT/'inputs.json').read_text('utf-8'));data={};runs={};summary={}
 for model in MODELS:
  path=OUT/(model+'.jsonl');data[model]=[json.loads(l) for l in path.read_text('utf-8').splitlines()] if path.exists() else []
  path=OUT/(model+'-run.json');runs[model]=json.loads(path.read_text('utf-8')) if path.exists() else dict(status='not run')
  times=[r['ms'] for r in data[model]]
  summary[model]=dict(status=runs[model]['status'],rows=len(data[model]),median_ms=statistics.median(times) if times else None,p95_ms=float(np.percentile(times,95)) if times else None,sampled_total_gpu_peak_mib=runs[model].get('gpu_total_peak_mib'),init_ms=runs[model].get('init_ms'))
  summary[model]['tasks']={}
  for task in sorted(set(r['task'] for r in data[model])):
   ts=[r['ms'] for r in data[model] if r['task']==task]
   summary[model]['tasks'][task]=dict(calls=len(ts),mean_ms=statistics.mean(ts),median_ms=statistics.median(ts),p95_ms=float(np.percentile(ts,95)),max_ms=max(ts))
 (OUT/'summary.json').write_text(json.dumps(summary,ensure_ascii=False,indent=2),'utf-8')
 table=[]
 for crop in suite['recognition']:
  cells=[]
  for model in ['baseline','ppocr6','manga']:
   rows=[r for r in data[model] if r['task']=='recognition-only' and r['id']==crop['id']]
   zero=next((r for r in rows if r['angle']==0),{})
   text=readings(zero.get('text','Unavailable'))
   anglelist='<br>'.join(f'{r["angle"]}°: {esc(readings(r["text"]))}' for r in rows)
   cells.append(f'<td><strong>{esc(text) or "∅"}</strong><details><summary>All six angles</summary>{anglelist}</details></td>')
  table.append(f'<tr><td><img class="crop" src="{crop["path"]}" alt="{esc(crop["id"])}"><br>{esc(crop["id"])}<br>Reference: {esc(crop["expected"]) or "no text"}</td>'+''.join(cells)+'</tr>')
 runtime=[]
 for m,r in summary.items():
  fmt=lambda v:'—' if v is None else f'{v:.0f}'
  for task,t in r['tasks'].items():
   runtime.append(f'<tr><td>{esc(m)} / {esc(task)}</td><td>{esc(r["status"])}</td><td>{t["calls"]}</td><td>{fmt(t["median_ms"])}</td><td>{fmt(t["p95_ms"])}</td><td>{fmt(r["sampled_total_gpu_peak_mib"]) if m!="baseline" else "CPU"}</td></tr>')
 yolo=[]
 for row in data['yolo']:
  if not row['predictions']:continue
  from PIL import ImageDraw
  scene=next(s for s in suite['discovery'] if s['id']==row['id']);im=Image.open(OUT/scene['path']).convert('RGB');draw=ImageDraw.Draw(im)
  for p in row['predictions']:
   draw.rectangle(p['box'],outline='#cc5500',width=2);draw.text((p['box'][0],max(0,p['box'][1]-14)),f'class {p["class_id"]}: {p["score"]:.2f}',fill='#993300')
  filename=f'yolo-{row["id"]}.png';im.save(OUT/filename)
  yolo.append(f'<figure><img src="{filename}" alt="YOLOE proposals on {esc(row["id"])}"><figcaption>{esc(row["id"])}. Class 0 = school reference; class 1 = hot-spring reference.</figcaption></figure>')
 dino=[]
 for row in data['dino']:
  if 'maps' not in row:continue
  scene=next(s for s in suite['discovery'] if s['id']==row['id']);base=Image.open(OUT/scene['path']).convert('RGB');images=[]
  for name,values in row['maps'].items():
   a=np.asarray(values);low,high=float(a.min()),float(a.max());a=(a-low)/max(1e-6,high-low);rgb=np.stack([a,np.zeros_like(a),1-a],axis=-1)
   heat=Image.fromarray((rgb*255).astype('uint8')).resize(base.size);blend=Image.blend(base,heat,.42);filename=f'dino-{row["id"]}-{name}.png';blend.save(OUT/filename)
   images.append(f'<figure><img src="{filename}"><figcaption>{esc(name)} · range {low:.2f}–{high:.2f}</figcaption></figure>')
  dino.append(f'<article><h3>{esc(row["id"])}</h3><div class="triptych">'+''.join(images)+'</div></article>')
 payload=json.dumps(dict(inputs=suite,results={k:v for k,v in data.items() if k!='dino'}),ensure_ascii=False).replace('</','<\\/')
 report='''<!doctype html><html lang="en"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>Small model trials · Wulai</title><style>
 body{background:#f8f7f1;color:#193c35;font:16px/1.6 system-ui;margin:0}main{max-width:1200px;margin:auto;padding:32px}h1{font:42px Georgia;margin:12px 0}h2{margin-top:40px}a{color:#17695b}.notice{background:#efe6c9;padding:18px 22px;border-left:4px solid #a47e27}table{border-collapse:collapse;width:100%;background:white}th,td{border-bottom:1px solid #dde2da;padding:12px;text-align:left;vertical-align:top}td{max-width:260px;overflow-wrap:anywhere}.crop{max-height:160px;max-width:150px}details{font-size:13px;color:#596d61}select{padding:10px;margin:8px 18px 16px 0}.comparison{display:grid;grid-template-columns:repeat(4,1fr);gap:12px}canvas{width:100%;height:auto;background:white}.readings{font-size:13px;max-height:130px;overflow:auto}.triptych{display:grid;grid-template-columns:repeat(3,1fr);gap:12px}figure{margin:0}img{max-width:100%}figcaption{font-size:13px}article{margin:24px 0}small{color:#576e62}@media(max-width:800px){.comparison,.triptych{grid-template-columns:1fr 1fr}main{padding:14px}table{font-size:13px}}
 </style><main><a href="../report.html">← Evidence notebook</a><h1>Small models on the GTX 1650</h1><p>Frozen Wulai imagery · rotated, sparse Kanji/Kana · 28 September 2026</p>
 <div class="notice"><strong>Experiments, not a production upgrade.</strong> A recognizer receiving a user-supplied crop has not discovered a landmark. Full-tile discovery is shown separately. All raw readings, empty results, failures and angle passes are retained.</div>
 <nav><a href="#recognition">Crop readings</a> · <a href="#discovery">Tile overlays</a> · <a href="#costs">Run costs</a> · <a href="#symbols">Symbols</a> · <a href="conclusions.md">Decisions</a></nav><p><strong>Decision: keep these models experimental.</strong> None has demonstrated reliable discovery of the missed labels. All five candidates ran with CUDA on this PC; detailed failures are preserved below.</p><h2 id="recognition">Recognition on the marked crops</h2><p>Bold readings use the original crop at 0°. Expand each cell for all rotations. Numbers in parentheses are model scores, not calibrated correctness probabilities. Manga OCR provides no comparable score here. No angle was selected using the expected answer. Raw low-confidence outputs are shown, including outputs the production threshold would reject. References and original pixels are independent evaluation inputs.</p>
 <table><thead><tr><th>Original crop / supplied reference</th><th>Current CPU baseline</th><th>PP-OCRv6 small</th><th>Manga OCR</th></tr></thead><tbody>'''+''.join(table)+'''</tbody></table>
 <h2 id="discovery">Full-tile discovery</h2><p>Models receive complete padded tiles, enlarged 2×. Overlays map results back to the native pixels. Orange: text with score ≥0.45. Gray: low-confidence reading. Blue: CRAFT region with no transcription. CRAFT boxes are proposals and may include contour fragments. Holdout scenes have no independent labels, so no holdout accuracy is claimed.</p>
 <label>Scene <select id="scene"></select></label><label>Rotation <select id="angle"></select></label>
 <div class="comparison">'''+''.join(f'<section><h3>{name}</h3><canvas id="{key}" width="384" height="384"></canvas><p class="readings" id="{key}-text"></p></section>' for key,name in [('original','Original'),('baseline','Baseline'),('ppocr6','PP-OCRv6'),('craft','CRAFT')])+'''</div>
 <h2 id="costs">Measured run costs</h2><p>These are observed call distributions, including first-shape overhead. Tasks differ: Manga is recognition-only; CRAFT is detection-only; DINO and YOLO use different tasks and inputs. They are not speedup comparisons. NVIDIA memory was sampled every 0.5 seconds and includes desktop/other GPU use; brief peaks can be missed. Inference ran one candidate at a time, but YOLO initialization/download monitoring overlapped CRAFT. The identical 2158 MiB peaks for those runs are therefore not isolated footprints. Initialization includes downloads; call timing excludes image loading and rotation but includes model preprocessing and decoding.</p>
 <table><thead><tr><th>Model</th><th>Status</th><th>Calls</th><th>Median ms</th><th>p95 ms</th><th>Sampled GPU peak MiB</th></tr></thead><tbody>'''+''.join(runtime)+'''</tbody></table>
 <h2 id="symbols">Symbol experiments</h2><p>YOLOE and DINO use school/hot-spring examples from the development symbol tile as explicit references. Results on that same image are positive controls, not independent accuracy. Neither model receives label readings. DINO maps below show similarity and local novelty, not landmark probability; colors are scaled separately per map.</p><p>YOLOE returned two school-class boxes: the supplied school example (0.26) and a false class assignment on ウ (0.28). The ウ box is still a useful artificial-mark candidate for this task despite its wrong class. It missed the supplied hot-spring example. Default confidence cutoff: 0.25. These results do not establish unknown-landmark detection.</p><div class="triptych">'''+''.join(yolo)+'''</div><pre id="yolo-summary"></pre>'''+''.join(dino)+'''
 <h2>Reproducibility</h2><p><a href="inputs.json">Frozen inputs and hashes</a> · <a href="summary.json">Run summary</a> · <a href="CONTRACT.md">Experiment contract</a> · <a href="downloads.json">Downloaded model revisions</a> · <a href="weights.json">Weight hashes</a> · <a href="environment.txt">Installed packages</a> · <a href="integrity.json">Integrity checks</a> · <a href="conclusions.md">Findings and decisions</a></p><p>Raw model files: baseline.jsonl, ppocr6.jsonl, craft.jsonl, manga.jsonl, dino.jsonl, yolo.jsonl. Matching *-run.json files contain configurations, provider checks, errors and memory samples. There is no automatic publication into the app's POI database.</p></main>
 <script>const data='''+payload+''';const scene=document.getElementById('scene'),angle=document.getElementById('angle');for(const s of data.inputs.discovery){const o=new Option(s.id+' / '+s.split,s.id);scene.add(o)}for(const a of data.inputs.angles)angle.add(new Option(a+'°',a));function render(){const s=data.inputs.discovery.find(s=>s.id===scene.value);const im=new Image();im.onload=()=>{for(const model of ['original','baseline','ppocr6','craft']){const c=document.getElementById(model),ctx=c.getContext('2d');ctx.clearRect(0,0,384,384);ctx.drawImage(im,0,0,384,384);const row=(data.results[model]||[]).find(r=>r.task==='discovery'&&r.id===s.id&&r.angle===Number(angle.value));const ps=row?.proposals||[];for(const p of ps){ctx.strokeStyle=model==='craft'?'#2459bb':p.score>=.45?'#dc850a':'#888';ctx.lineWidth=2;ctx.beginPath();p.polygon.forEach((p,i)=>i?ctx.lineTo(...p):ctx.moveTo(...p));ctx.closePath();ctx.stroke()}document.getElementById(model+'-text').textContent=model==='original'?'Native source pixels':ps.length+' proposals. '+ps.map(p=>p.text?`${p.text} (${p.score?.toFixed(2)})`:'unread region').join(' · ')}};im.src=s.path}scene.onchange=render;angle.onchange=render;render();document.getElementById('yolo-summary').textContent=(data.results.yolo||[]).map(r=>r.id+': '+(r.predictions?.length||0)+' proposals').join('\\n');</script></html>'''
 (OUT/'report.html').write_text(report,'utf-8')
 print(json.dumps(summary,indent=2))
if __name__=='__main__':main()
