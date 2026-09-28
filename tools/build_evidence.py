"""Controlled ablations on real inputs. Does not use review labels for inference."""
import html
import importlib.metadata
import json
import platform
import statistics
import sys
import time
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw, ImageFont

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from mapwalker.db import Store
from mapwalker.detectors import CONFIG, TextDetector, developed_mask, filter_proposals, specs, symbol_proposals
from mapwalker.geo import pixel_lonlat
from mapwalker.junctions import junction_proposals
from mapwalker.trails import trail_proposals
from mapwalker.angled import angled_text_proposals
from mapwalker.paths import default_data
from mapwalker.sources import HISTORICAL, TileCache
from mapwalker.worker import Worker


def main():
    folder=ROOT/'evidence';folder.mkdir(exist_ok=True)
    registry=specs()
    cache=TileCache(default_data())
    store=Store(default_data()/'mapwalker.sqlite3');store.register(registry)
    worker=Worker(store,cache)
    # Holdout coordinates fixed here AFTER method proposal, before downloading.
    scenes=[('town','development',54895,28092),('mountain','development',54899,28096),
            ('fresh-boundary','initial-holdout',54896,28094),
            ('fresh-north','holdout-after-junction-proposal',54894,28089),
            ('fresh-trails','holdout-after-trail-proposal',54898,28089),
            ('skewed-creek','user-identified-development',54895,28091)]
    rows=[]
    font_path=Path('C:/Windows/Fonts/msjh.ttc')
    font=ImageFont.truetype(str(font_path),17) if font_path.exists() else ImageFont.load_default()
    engine=TextDetector()
    for name,split,x,y in scenes:
        for source in HISTORICAL:
            print(name,source,flush=True)
            hist,hm,ht=cache.mosaic(source,16,x,y)
            modern,mm,mt=cache.mosaic('EMAP',16,x,y)
            mask=developed_mask(modern)
            tick=time.perf_counter();texts=engine(hist);ocr_ms=(time.perf_counter()-tick)*1000
            tick=time.perf_counter();symbols=symbol_proposals(hist);symbol_ms=(time.perf_counter()-tick)*1000
            proposals=texts+symbols
            baseline=filter_proposals(proposals,mask,repetition=False,urban=False)
            repeat=filter_proposals(proposals,mask,repetition=True,urban=False)
            final=filter_proposals(proposals,mask,repetition=True,urban=True)
            tick=time.perf_counter();extra=junction_proposals(hist,CONFIG);junction_ms=(time.perf_counter()-tick)*1000
            extra_filtered=filter_proposals(extra,mask,repetition=True,urban=True)
            combined=final+extra_filtered
            tick=time.perf_counter();trails=trail_proposals(hist,CONFIG);trail_ms=(time.perf_counter()-tick)*1000
            trail_filtered=filter_proposals(trails,mask,repetition=True,urban=True)
            combined_with_trails=combined+trail_filtered
            tick=time.perf_counter();angled=angled_text_proposals(hist,CONFIG,engine);angled_ms=(time.perf_counter()-tick)*1000
            angled_filtered=filter_proposals(angled,mask,repetition=True,urban=True)
            all_findings=combined_with_trails+angled_filtered
            row=dict(scene=name,split=split,source=source,z=16,x=x,y=y,
                     baseline=len(baseline),repeat=sum(p['disposition']=='candidate' for p in repeat),
                     final=sum(p['disposition']=='candidate' for p in final),
                     with_junctions=sum(p['disposition']=='candidate' for p in combined),
                     with_trails=sum(p['disposition']=='candidate' for p in combined_with_trails),
                     with_angles=sum(p['disposition']=='candidate' for p in all_findings),
                     angled_ms=angled_ms,angled_findings=angled_filtered,
                     trail_ms=trail_ms,trail_findings=trail_filtered,
                     junction_ms=junction_ms,junction_findings=extra_filtered,
                     text=sum(p['kind']=='text' for p in final),symbol=sum(p['kind']=='symbol' for p in final),
                     boundary_retained=sum(p['details']['boundary_review'] for p in final),
                     modern_mask_fraction=float(mask.mean()),ocr_ms=ocr_ms,symbol_ms=symbol_ms,
                     io_ms=ht['io_ms']+mt['io_ms'],decode_ms=ht['decode_ms']+mt['decode_ms'],
                     inputs=hm+mm,baseline_findings=baseline,repeat_findings=repeat,final_findings=final)
            sheet=Image.new('RGB',(384*3,444),'#f6f5ed');draw=ImageDraw.Draw(sheet)
            sheet.paste(hist,(0,60));sheet.paste(modern,(384,60))
            tinted=modern.copy();tinted.paste(Image.new('RGB',modern.size,'#e25143'),mask=Image.fromarray((mask*125).astype('uint8')))
            sheet.paste(tinted,(768,60))
            draw.text((12,8),f'{name} / {split} / {source} / z16 {x} {y}',font=font,fill='#173c32')
            for offset,title in [(0,'Historical proposals'),(384,'Modern NLSC'),(768,'Developed mask (experimental)')]:
                draw.text((offset+12,34),title,font=font,fill='#53645a')
            for index,p in enumerate(all_findings):
                box=p['box'];color='#c84130' if p['disposition']=='excluded' else '#128a63' if p['kind']=='symbol' else '#b37a12'
                if p['kind']=='trail':
                    draw.line([(px,py+60) for px,py in p['details']['pixel_path']],fill='#7550ae',width=3)
                else:
                    draw.rectangle([box[0]+64,box[1]+124,box[2]+64,box[3]+124],outline=color,width=2)
            filename=f'{name}-{source}.jpg';sheet.save(folder/filename,quality=94)
            row['image']=filename;rows.append(row)
            store.enqueue(source,[(16,x,y)])
    # Production path replay uses exactly the same immutable cache and active registry.
    while worker.once():
        pass
    environment=dict(python=platform.python_version(),platform=platform.platform(),
                     packages={p:importlib.metadata.version(p) for p in ['numpy','pillow','opencv-python','rapidocr-onnxruntime','onnxruntime']})
    artifact=dict(created_at=time.time(),environment=environment,algorithms=registry,rows=rows,status=store.status(),
                  independent_accuracy='UNMEASURED: no independently annotated real-map reference',
                  decisions={'OCR':'retain for review; historical script accuracy unmeasured',
                             'symbols':'retain experimental artificial-mark proposals; contours may be false positives',
                             'repetition':'retain experimental; controlled synthetic mechanism test only',
                             'trails':'retain experimental segment proposals; synthetic dash preservation and raw imagery only',
                             'angled-text':'retain experimental; narrow user-identified creek recovery; general accuracy unmeasured',
                             'urban':'retain experimental with displacement margin; uncalibrated raster style heuristic'})
    (folder/'experiment.json').write_text(json.dumps(artifact,ensure_ascii=False,indent=2),'utf-8')
    with store.connect() as db:
        telemetry=[dict(r) for r in db.execute('''SELECT j.id,t.source,t.z,t.x,t.y,a.name,j.state,j.telemetry,j.error FROM jobs j
             JOIN tiles t ON t.id=j.tile_id JOIN algorithms a ON a.fingerprint=j.algorithm WHERE a.active=1''')]
    (folder/'run-telemetry.json').write_text(json.dumps(telemetry,ensure_ascii=False,indent=2),'utf-8')
    table=''.join(f'<tr><td>{r["scene"]}<br><small>{r["split"]}</small></td><td>{r["source"]}</td><td>{r["baseline"]}</td><td>{r["repeat"]}</td><td>{r["final"]}</td><td>{r["with_junctions"]}</td><td>{r["with_trails"]}</td><td>{r["with_angles"]}</td><td>{r["boundary_retained"]}</td><td>{r["ocr_ms"]:.0f}</td><td>{r["symbol_ms"]:.0f}</td></tr>' for r in rows)
    panels=''.join(f'<article><h3>{r["scene"]} · {r["source"]}</h3><p>{r["split"]} · Tile 16 / {r["x"]} / {r["y"]}. Green: shape proposal. Ochre: OCR text. Red: excluded proposal. Purple: trail segment proposal.</p><a href="{r["image"]}"><img src="{r["image"]}" alt="Historical proposals next to modern NLSC and developed mask"></a></article>' for r in rows)
    timings=[]
    for row in telemetry:
        if row['telemetry']:timings.append(json.loads(row['telemetry'])['total_ms'])
    latency='' if not timings else f'Mean {statistics.mean(timings):.0f} ms · median {statistics.median(timings):.0f} ms · p95 {np.percentile(timings,95):.0f} ms · max {max(timings):.0f} ms.'
    report=f'''<!doctype html><html lang="en"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>Mapwalker evidence notebook</title><style>body{{font:15px/1.65 'Segoe UI',sans-serif;color:#183b33;background:#f6f5ed;margin:0}}main{{max-width:1200px;margin:auto;padding:45px 30px}}h1{{font:42px Georgia,serif}}h2{{margin-top:36px}}small,p{{color:#62736a}}a{{color:#237963}}.notice{{border-left:4px solid #b6833d;background:#eee7d8;padding:18px 24px}}table{{border-collapse:collapse;width:100%;font-size:12px;background:#fff}}th,td{{padding:12px;text-align:left;border-bottom:1px solid #dce1d4}}img{{max-width:100%;border-radius:8px}}article{{margin:30px 0;background:#fff;padding:22px;border:1px solid #dce1d4;border-radius:10px}}.links{{display:flex;gap:20px;flex-wrap:wrap}}</style><main><a href="/">← Open map</a><p>MAPWALKER / EVIDENCE NOTEBOOK / 2026-09-28</p><h1>What the maps actually show.</h1><div class="notice"><strong>Real imagery. Experimental findings. Accuracy unmeasured.</strong><br>These twelve paired scenes document what was downloaded and what each filter did. They do not establish precision or recall. Review original pixels, including excluded candidates. 文 can mean a school; a detected glyph is not necessarily a place name.</div><h2>Controlled comparisons</h2><p>Baseline uses OCR and compact dark components. A adds only repetition suppression. B holds A fixed and adds NLSC developed-area exclusion, retaining a 16-pixel boundary margin (~35 m at Wulai). Identical frozen inputs and detector proposals are used for each comparison. C adds only a junction-cluster proposal algorithm to recover marks attached to long contours. D adds aligned-dash trail segments. E adds ±45-degree OCR; original coordinates are recovered with the inverse rotation. Repeated dashes near detected trails are protected from pattern suppression. Counts measure filter behavior, not accuracy.</p><table><thead><tr><th>Scene / split</th><th>Layer</th><th>Baseline</th><th>A: repeats</th><th>B: developed</th><th>C: + junctions</th><th>D: + trails</th><th>E: ±45° text</th><th>Boundary review</th><th>OCR ms</th><th>Shapes ms</th></tr></thead><tbody>{table}</tbody></table><h2>Decisions and limitations</h2><ul><li>Infrastructure: retain after restart, ownership, version, viewport and atomic-publication tests.</li><li>Detection: retain as experimental proposals for review. A compact ink component may be a contour fragment. OCR may miss vertical, old or blurred text; semantics remain unknown.</li><li>Negative result: the repetition filter removed zero proposals from the first six real scenes. Vegetation suppression is not demonstrated.</li><li>Repetition: synthetic tests establish the mechanism, not that every rejected repeated mark is vegetation. Repeated meaningful landmarks can be false exclusions.</li><li>Developed-area mask: lavender NLSC building pixels and local density are a heuristic. The boundary margin is not an error bound. Larger historical displacement can still cause false exclusions.</li><li>Historical layers have different content and local displacement. Coordinates are not surveyed POI locations. No cross-layer proximity merge or snapping is performed.</li><li>Fresh holdout: two initial tiles after freezing the baseline, then two additional northern tiles after proposing junction detection, and two more after proposing trail detection. No threshold tuning on either holdout. Independent manual ground truth is still missing.</li><li>Not a performance comparison: OCR initialization and cache warming differ. No claimed speedup. Download, decode, model initialization, detection and filter timings are separate in raw telemetry.</li></ul><h2>Your school and hot-spring examples</h2><p>The compact-component baseline captures the school 文, which the NLSC filter excludes inside modern development. It misses the hot-spring symbol because that ink component connects to a long contour. A separate junction proposal recovers part of that mark. These two user-identified examples are development probes, not an accuracy test. The extra algorithm can also find contour intersections, so remains experimental.</p><p><a href="junction-experiment.png">Inspect red reference boxes and blue extra proposals</a> · <a href="junction-experiment.json">Reference boxes and match results</a> · <a href="baseline-v1/report.html">Preserved first baseline report</a></p><h2>Trails and Japanese text</h2><p>Dashed trails are meaningful repeated structures. Purple line proposals preserve aligned dash chains and are exported as line geometry. These are not validated routes; text strokes and contour fragments can resemble dashes. The user-identified vertical label ウライ社 is not reliably read by this OCR. Rotating the development image 90/270 degrees also produced no recognized text. This negative result is retained; the known name is never inserted into runtime results.</p><h2>Skewed text and right-to-left readings</h2><p>In the user-identified creek tile, upright OCR reads K, while the -45-degree pass reads 溪. This narrow recovery is supported by the original pixels; general text accuracy is unmeasured. The supplied RTL 桶後溪 is a reference, not an injected result. Horizontal multi-character CJK readings offer a possible reversed reading without overwriting raw OCR. Text labels sort first.</p><p><a href="skewed-creek-probe.png">Inspect the skewed 溪</a> · <a href="skewed-creek-probe.json">Raw before/after OCR</a> · <a href="angled-text-probe.json">Angle experiment on earlier scenes</a> · <a href="vertical-label-probe.json">Centered vertical-label experiment</a></p><h2>Production replay</h2><p>{html.escape(json.dumps(store.status()['counts']))}. {latency} These are cached-input replay timings. Zero-candidate successes are recorded; no previous outputs count as fresh detections.</p><div class="links"><a href="experiment.json">Full experiment & input SHA-256s</a><a href="run-telemetry.json">Production telemetry</a><a href="CONTRACT.md">Acceptance contract</a><a href="test-results.txt">Test results</a><a href="sources/onlinemapsources.xml">Published layer zoom limits</a></div><h2>Inspect the inputs and proposals</h2>{panels}</main></html>'''
    report=report.replace('<h2>Controlled comparisons</h2>', '<p><a href="user-review/report.html">Review your eight marked landmarks: before and after full-view processing</a></p><h2>Controlled comparisons</h2>')
    (folder/'report.html').write_text(report,'utf-8')
    print(json.dumps(store.status(),ensure_ascii=False),flush=True)


if __name__=='__main__':main()
