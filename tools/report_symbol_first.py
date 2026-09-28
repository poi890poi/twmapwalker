"""Post-run review only. References never enter proposal generation."""
import json,html,hashlib,statistics
from pathlib import Path
import numpy as np
from run_symbol_first import iou,deduplicate
ROOT=Path(__file__).resolve().parents[1];OUT=ROOT/'evidence/symbol-first'
MODELS={'baseline-symbols':'Current symbols','ppocr-det':'PP-OCRv6 detection','craft-char':'CRAFT character regions','stable-ink':'Stable ink regions'}
def retained(p):return not p.get('repeating',False) or p.get('details',{}).get('trail_context',False)
def main():
 suite=json.loads((OUT/'inputs.json').read_text('utf-8'));refs=json.loads((OUT/'references.json').read_text('utf-8'));data={};summary={};runs={}
 for m in MODELS:
  data[m]=[json.loads(l) for l in (OUT/(m+'.jsonl')).read_text('utf-8').splitlines()]
  run=json.loads((OUT/(m+'-run.json')).read_text('utf-8'));runs[m]=run
  times=[r['total_inference_ms'] for r in data[m]];counts=[sum(retained(p) for p in r['proposals']) for r in data[m]]
  coverage=[]
  for ref in refs['marks']:
   row=next((r for r in data[m] if r['scene']==ref['scene']),{'proposals':[]})
   matches=[(iou(ref['box'],p['box']),p) for p in row['proposals'] if retained(p)]
   best=max(matches,key=lambda x:x[0],default=(0,None))
   coverage.append(dict(scene=ref['scene'],label=ref['label'],best_iou=best[0],matched=best[0]>=refs['match_iou'],proposal=best[1]))
  summary[m]=dict(status=run['status'],scenes=len(data[m]),matched=sum(c['matched'] for c in coverage),references=len(coverage),coverage=coverage,total_proposals=sum(counts),median_proposals=statistics.median(counts),max_proposals=max(counts),mean_tile_ms=statistics.mean(times),median_tile_ms=statistics.median(times),p95_tile_ms=float(np.percentile(times,95)),max_tile_ms=max(times),gpu_peak_mib=run.get('gpu_total_peak_mib'))
 # Evaluate the previous CRAFT word-region run on the same fixed references.
 old=[json.loads(l) for l in (ROOT/'evidence/model-trials/craft.jsonl').read_text('utf-8').splitlines()]
 old_by_scene={}
 for r in old:
  for p in r['proposals']:
   xy=p['polygon'];box=[min(a[0] for a in xy),min(a[1] for a in xy),max(a[0] for a in xy),max(a[1] for a in xy)]
   old_by_scene.setdefault(r['id'],[]).append(dict(box=box,score=0))
 old_coverage=[]
 for ref in refs['marks']:
  best=max([iou(ref['box'],p['box']) for p in old_by_scene.get(ref['scene'],[])],default=0)
  old_coverage.append(dict(label=ref['label'],best_iou=best,matched=best>=refs['match_iou']))
 comparison=dict(prior_default_matched=sum(r['matched'] for r in old_coverage),character_policy_matched=summary['craft-char']['matched'],references=10,prior_coverage=old_coverage,scope='same known development marks; thresholds and region grouping change together, weights and image passes unchanged')
 (OUT/'craft-postprocessing-comparison.json').write_text(json.dumps(comparison,ensure_ascii=False,indent=2),'utf-8')
 (OUT/'summary.json').write_text(json.dumps(summary,ensure_ascii=False,indent=2),'utf-8')
 refrows=[]
 for index,ref in enumerate(refs['marks']):
  cells=[]
  for m in MODELS:
   c=summary[m]['coverage'][index];cells.append(f'<td class="{"hit" if c["matched"] else "miss"}">{"Located" if c["matched"] else "Miss"} <small>IoU {c["best_iou"]:.2f}</small></td>')
  refrows.append(f'<tr><th>{html.escape(ref["label"])}</th>'+''.join(cells)+'</tr>')
 runtime=[]
 for m,s in summary.items():
  runtime.append(f'<tr><th>{MODELS[m]}</th><td>{s["matched"]}/10</td><td>{s["total_proposals"]}</td><td>{s["median_proposals"]:g} / {s["max_proposals"]}</td><td>{s["median_tile_ms"]:.0f}</td><td>{s["p95_tile_ms"]:.0f}</td></tr>')
 payload=json.dumps(dict(inputs=suite,refs=refs,results=data),ensure_ascii=False).replace('</','<\\/')
 report='''<!doctype html><html lang="en"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>Find marks first · Wulai</title><style>
 body{margin:0;background:#f8f7f1;color:#173e34;font:16px/1.55 system-ui}main{max-width:1280px;margin:auto;padding:28px}h1{font:44px Georgia;margin:12px 0}h2{margin-top:36px}a{color:#17695b}.notice{padding:16px 20px;background:#eee5cb;border-left:4px solid #ad842b}.controls{display:flex;flex-wrap:wrap;gap:20px;align-items:center;margin:20px 0}select{padding:10px;max-width:100%}.grid{display:grid;grid-template-columns:repeat(4,1fr);gap:12px}h3{font-size:17px}canvas{width:100%;height:auto;cursor:crosshair}.count{font-size:14px}.crop-review{display:flex;gap:24px;background:white;padding:16px;margin-top:24px;align-items:center}.crop-review canvas{width:180px;height:180px;flex-shrink:0}table{width:100%;border-collapse:collapse;background:white}td,th{padding:10px;border-bottom:1px solid #d8dfd3;text-align:left}.hit{color:#19703f}.miss{color:#8f522d}small{display:block;color:#637467;font-size:12px}.table-wrap{overflow:auto}nav{margin:18px 0}pre{white-space:pre-wrap}.details{color:#486253;font-size:14px}@media(max-width:850px){.grid{grid-template-columns:1fr 1fr}main{padding:14px}.crop-review{align-items:flex-start}h1{font-size:34px}}
 </style><main><a href="../model-trials/report.html">← Model trials</a><h1>Find marks first. Read them later.</h1><p>Wulai · both historical map series · GTX 1650 · 28 September 2026</p>
 <div class="notice"><strong>No reading or symbol name required.</strong> These experiments propose regions directly from full tile pixels. User references are used only after inference for evaluation. None of these results is published into the production POI database.</div>
 <nav><a href="#regions">Region comparison</a> · <a href="#references">Known marks</a> · <a href="#costs">Proposal burden</a> · <a href="conclusions.md">Findings and decisions</a></nav>
 <h2 id="regions">Region comparison</h2><p>Blue: unread candidate. Gray: repeated-shape flag. Green: evaluation reference. Click a box to inspect its original crop. Boxes beyond image bounds are clipped to the edge for display. Scores describe the model or stability measurement; they are not probabilities that a mark is artificial. A box on contours is still a false-looking proposal, even when its score is high.</p>
 <div class="controls"><label for="scene">Map scene</label><select id="scene"></select><label><input id="refs" type="checkbox" checked> Show evaluation references</label><label><input id="repeats" type="checkbox"> Show repetition flags</label></div>
 <div class="grid">'''+''.join(f'<section><h3>{name}</h3><canvas width="384" height="384" id="{m}" aria-label="{name} proposals"></canvas><p class="count" id="{m}-count"></p></section>' for m,name in MODELS.items())+'''</div>
 <div class="crop-review"><canvas id="crop" width="180" height="180" aria-label="Selected source crop"></canvas><div><strong>Inspect an unread mark</strong><p id="crop-info">Click any proposed region above. The crop remains a candidate even when no recognizer can read it.</p></div></div>
 <p><strong>CRAFT postprocessing check:</strong> the previous default word-region output locates 2/10 of these same marks; the character-region policy locates 7/10. Both thresholds and grouping changed, so this does not isolate their individual contributions. <a href="craft-postprocessing-comparison.json">Comparison data</a>.</p><h2 id="references">Coverage of ten known development marks</h2><p>Ten partial, manually boxed user examples. “Located” requires box intersection-over-union ≥0.25. It does not prove the detector understood the mark, and these examples are not exhaustive ground truth. The four new scenes are unannotated visual transfer checks. Wide boxes covering whole tiles do not count as localized marks.</p>
 <div class="table-wrap"><table><thead><tr><th>Known mark</th>'''+''.join(f'<th>{name}</th>' for name in MODELS.values())+'''</tr></thead><tbody>'''+''.join(refrows)+'''</tbody></table></div>
 <h2 id="costs">Coverage must be weighed against review burden</h2><p>Counts follow rotation deduplication, omit repetition-flagged shapes unless protected by the existing trail context, and include the 64px halo. They are review proposals, not final POIs. Timings include all six passes for the neural methods; pixel methods use one pass. No speedup claim is made.</p>
 <div class="table-wrap"><table><thead><tr><th>Method</th><th>Known marks</th><th>All proposals / 15 tiles</th><th>Median / max per tile</th><th>Median ms/tile</th><th>p95 ms/tile</th></tr></thead><tbody>'''+''.join(runtime)+'''</tbody></table></div>
 <h2>Evidence</h2><p><a href="CONTRACT.md">Contract</a> · <a href="inputs.json">Frozen input hashes</a> · <a href="references.json">Independent review boxes</a> · <a href="summary.json">Measurements</a> · <a href="conclusions.md">Decisions and limitations</a> · <a href="../model-trials/weights.json">Checkpoint hashes</a> · <a href="../model-trials/environment.txt">Installed packages</a></p><p class="details">Raw per-angle boxes and times: baseline-symbols.jsonl, ppocr-det.jsonl, craft-char.jsonl, stable-ink.jsonl. Matching run metadata and harness snapshots preserve setup and failures. The detector script never reads references.json.</p></main>
 <script>const data='''+payload+''';const models='''+json.dumps(MODELS)+''';const scene=document.getElementById('scene');let activeImage=null;let displayed={};for(const s of data.inputs.scenes)scene.add(new Option(s.id+' / '+s.split,s.id));function keep(p){return !p.repeating||p.details?.trail_context}function render(){const s=data.inputs.scenes.find(s=>s.id===scene.value),im=new Image();im.onload=()=>{activeImage=im;for(const m of Object.keys(models)){const row=data.results[m].find(r=>r.scene===s.id);const all=row?.proposals||[];const ps=all.filter(p=>document.getElementById('repeats').checked||keep(p));displayed[m]=ps;const ctx=document.getElementById(m).getContext('2d');ctx.clearRect(0,0,384,384);ctx.drawImage(im,0,0,384,384);for(const p of ps){ctx.strokeStyle=keep(p)?'#2663be':'#888';ctx.lineWidth=1.5;const b=p.box;const x0=Math.max(1,b[0]),y0=Math.max(1,b[1]),x1=Math.min(383,b[2]),y1=Math.min(383,b[3]);ctx.strokeRect(x0,y0,x1-x0,y1-y0)}if(document.getElementById('refs').checked){ctx.strokeStyle='#22974b';ctx.lineWidth=2;ctx.setLineDash([4,3]);for(const ref of data.refs.marks.filter(r=>r.scene===s.id)){const b=ref.box;ctx.strokeRect(b[0],b[1],b[2]-b[0],b[3]-b[1])}ctx.setLineDash([])}document.getElementById(m+'-count').textContent=all.filter(keep).length+' candidates · '+all.filter(p=>!keep(p)).length+' repetition flags'+(all.some(p=>(p.box[2]-p.box[0])*(p.box[3]-p.box[1])>384*384*.5)?' · includes a region covering most of the tile':'');}document.getElementById('crop-info').textContent='Click any proposed region above.';document.getElementById('crop').getContext('2d').clearRect(0,0,180,180)};im.src=s.path}for(const m of Object.keys(models)){document.getElementById(m).onclick=e=>{const c=e.currentTarget,bounds=c.getBoundingClientRect(),x=(e.clientX-bounds.left)*384/bounds.width,y=(e.clientY-bounds.top)*384/bounds.height;const ps=(displayed[m]||[]).filter(p=>x>=p.box[0]&&x<=p.box[2]&&y>=p.box[1]&&y<=p.box[3]).sort((a,b)=>(a.box[2]-a.box[0])*(a.box[3]-a.box[1])-(b.box[2]-b.box[0])*(b.box[3]-b.box[1]));if(!ps.length)return;const p=ps[0],b=p.box,crop=document.getElementById('crop'),ctx=crop.getContext('2d'),side=Math.max(b[2]-b[0],b[3]-b[1])+20;ctx.fillStyle='#fff';ctx.fillRect(0,0,180,180);ctx.drawImage(activeImage,(b[0]+b[2]-side)/2,(b[1]+b[3]-side)/2,side,side,0,0,180,180);document.getElementById('crop-info').textContent=models[m]+' · unread region · score '+p.score.toFixed(3)+(p.support?' · survives '+p.support.length+' thresholds':'')+' · proposal box '+b.map(v=>v.toFixed(0)).join(', ')+'. No reading has been requested.'}}scene.onchange=render;document.getElementById('refs').onchange=render;document.getElementById('repeats').onchange=render;render();</script></html>'''
 (OUT/'report.html').write_text(report,'utf-8')
 print(json.dumps({m:{k:v for k,v in s.items() if k!='coverage'} for m,s in summary.items()},indent=2))
if __name__=='__main__':main()
