"""Preserve failed trials; verify locked inputs and report the bounded landing."""
import gzip,hashlib,html,importlib.util,json,platform,sqlite3,statistics
from collections import Counter
from pathlib import Path
import cv2,numpy as np,PIL
from PIL import Image
import component_vegetation_trial as trial
from audit_vegetation_evidence import automatic
from mapwalker.reading_suggestions import evidence_crop
from mapwalker.vegetation import analyze
from mapwalker.vegetation_evidence import VegetationEvidence
ROOT=trial.ROOT;OUT=trial.OUT;old=trial.old

def read(path):return json.loads(Path(path).read_text('utf-8-sig'))
def write(name,value):(OUT/name).write_text(json.dumps(value,ensure_ascii=False,indent=2),'utf-8')
def stats(values):return dict(mean=statistics.mean(values),median=statistics.median(values),p95=float(np.percentile(values,95)),maximum=max(values))

def main():
    lock=read(OUT/'candidate-v2-lock.json')
    for name,digest in lock['code'].items():assert old.digest(ROOT/'mapwalker'/name)==digest
    first=read(OUT/'fresh/dataset.json');fresh=read(OUT/'fresh-v2/dataset.json');labels=read(OUT/'fresh-v2/visual-labels.json')['labels']
    assert set(labels)=={str(r['id']) for r in fresh}
    assert len({(r['source'],r['x']//4,r['y']//4) for r in fresh})==len(fresh)
    for r in trial.rows()+first+fresh:assert old.digest(r['image'])==r['sha256']
    previous=[r for r in trial.rows()+first+read(ROOT/'evidence/symbol-first/inputs.json')['scenes'] if 'source' in r]
    def bounds(r):
        b=r.get('box',[-256,-256,512,512]);return [r['x']*256+b[0]-64,r['y']*256+b[1]-64,r['x']*256+b[2]+64,r['y']*256+b[3]+64]
    for r in fresh:
        b=bounds(r)
        for a in previous:
            if (r['source'],r['z'])!=(a['source'],a['z']):continue
            c=bounds(a);assert not(b[0]<c[2] and c[0]<b[2] and b[1]<c[3] and c[1]<b[3])
    db=sqlite3.connect('file:'+str(ROOT/'data/mapwalker.sqlite3').replace('\\','/')+'?mode=ro',uri=True);db.row_factory=sqlite3.Row
    service=VegetationEvidence(ROOT/'data');replayed=[]
    for r in fresh:
        result=service.inspect(automatic(db,r['id']));result.pop('preview',None)
        assert (result['status'],result['matches'])==(r['prediction']['status'],r['prediction']['matches'])
        replayed.append(dict(id=r['id'],status=result['status']))
    spec=importlib.util.spec_from_file_location('frozen_v1',OUT/'candidate-v1.py');v1=importlib.util.module_from_spec(spec);spec.loader.exec_module(v1)
    ablations=[]
    for pid in (53137,44253):
        item=automatic(db,pid);im,box,_=evidence_crop(ROOT/'data',item,24)
        final=service.inspect(item)
        ablations.append(dict(id=pid,v1_geometry=bool(v1.analyze(im,box,16)['matches']),minimum_height_only=bool(analyze(im,box,16)['matches']),with_number_guard=bool(final['matches']),final_status=final['status']))
    db.close();write('failure-ablations.json',ablations)
    reused=read(OUT/'candidate-v2-reused.json');firstlabels=read(OUT/'fresh/visual-labels.json')['labels']
    def summary(rows,label,predict):
        return {l:dict(total=sum(label(r)==l for r in rows),suggested=sum(label(r)==l and bool(predict(r)) for r in rows)) for l in sorted({label(r) for r in rows})}
    totals=dict(v1_first_check=summary(first,lambda r:firstlabels[str(r['id'])],lambda r:r['prediction']['matches']),v2_reused=summary(reused,lambda r:r['label'],lambda r:r['matches']),v2_fresh=summary(fresh,lambda r:labels[str(r['id'])],lambda r:r['prediction']['matches']))
    assert all(not r['prediction']['matches'] or labels[str(r['id'])]=='vegetation-like' for r in fresh)
    write('summary.json',totals)
    timing=dict(full_service_fresh_ms=stats([r['ms'] for r in fresh]),no_match_ms=stats([r['ms'] for r in fresh if r['prediction']['status']=='no-match']),geometry_positive_ms=stats([r['ms'] for r in fresh if r['stratum']=='geometry-positive']),input_ms=stats([r['prediction']['timing_ms']['input'] for r in fresh]),geometry_ms=stats([r['prediction']['timing_ms']['analysis'] for r in fresh]),number_guard_ms=stats([r['prediction']['timing_ms']['number_guard'] for r in fresh if 'number_guard' in r['prediction']['timing_ms']]),scope='Sequential desktop CPU; includes cold model startup once, image decoding and preview encoding. Includes audit crop encoding/writing; no browser/network latency or throughput claim.')
    write('timing-summary.json',timing)
    # Lossless compression preserves the exact large mask arrays without repository bloat.
    compressed=[];variant_rows=[]
    for name in ('evaluation','opening','evaluation-footprint','opening-footprint'):
        source=OUT/(name+'.json');dest=OUT/(name+'.json.gz')
        if source.exists():
            payload=source.read_bytes();dest.write_bytes(gzip.compress(payload,mtime=0));assert gzip.decompress(dest.read_bytes())==payload
            source.unlink() # Only this run's generated and verified, losslessly archived output.
        payload=gzip.decompress(dest.read_bytes());rr=json.loads(payload)
        compressed.append(dict(file=dest.name,raw_sha256=hashlib.sha256(payload).hexdigest(),raw_bytes=len(payload)))
        for field in ('shape','compound'):
            hits=[r for r in rr if r[field]];variant_rows.append(dict(variant=name,gate=field,vegetation=sum(r['label']=='vegetation-like' for r in hits),other=[dict(id=r['id'],label=r['label']) for r in hits if r['label']!='vegetation-like']))
    write('trial-summary.json',dict(compression=compressed,variants=variant_rows))
    import rapidocr_onnxruntime,onnxruntime
    write('environment.json',dict(python=platform.python_version(),opencv=cv2.__version__,numpy=np.__version__,pillow=PIL.__version__,onnxruntime=onnxruntime.__version__,reader_models={p.name:old.digest(p) for p in (Path(rapidocr_onnxruntime.__file__).parent/'models').glob('*.onnx')}))
    write('verification.json',dict(checks=['332 frozen input hashes verified','36 full-service results replayed against production code','36 distinct 4x4 blocks; no overlap with earlier crops including 64px reader context','Locked v2 code hashes verified','One-variable failure probes preserve digit 9 until number guard vetoes it'],replay=replayed,decision='Land on-demand advisory only; no automatic rejection, hiding, backfill or detection fingerprint change. User must choose Other and then Save.',limitations='Assistant visual labels; selection enriched for geometry matches. Same two map editions and partly nearby regions. Not human ground truth, prevalence, recall, confidence calibration or an estimate of real-world precision.'))
    table=''.join(f"<tr><td>{html.escape(r['variant'])} / {r['gate']}</td><td>{r['vegetation']}</td><td>{html.escape(str(r['other']))}</td></tr>" for r in variant_rows)
    cards=''.join(f'<figure><img src="fresh-v2/{r["crop"]}" alt="Original crop {r["id"]}"><figcaption>#{r["id"]} · {html.escape(labels[str(r["id"])])}<br>{r["prediction"]["status"]}</figcaption></figure>' for r in fresh if r['stratum']=='geometry-positive')
    ms=timing['geometry_positive_ms'];no=timing['no_match_ms']
    (OUT/'report.html').write_text(f'''<!doctype html><html lang="en"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>Vegetation review — landed method · Mapwalker</title>
<style>body{{font:17px/1.6 system-ui;margin:0;color:#17322f;background:#f4f4eb}}main{{max-width:1100px;margin:auto;padding:32px 20px}}h1{{font-size:clamp(28px,4vw,46px);line-height:1.15}}h2{{line-height:1.2}}section{{background:white;padding:24px;margin:24px 0;border:1px solid #d8dfd7;border-radius:12px}}a{{color:#146451}}table{{border-collapse:collapse;width:100%;font-size:14px}}td,th{{border-bottom:1px solid #d8dfd7;padding:10px;text-align:left}}.scroll{{overflow:auto}}.cards{{display:grid;grid-template-columns:repeat(auto-fit,minmax(160px,1fr));gap:14px}}figure{{margin:0}}figure img{{width:100%;height:165px;object-fit:contain;image-rendering:pixelated;background:#eee}}figcaption{{font-size:14px}}.wide{{width:100%;height:auto}}.lead{{font-size:21px}}code{{overflow-wrap:anywhere}}</style><main>
<p>MAPWALKER / EVIDENCE / 03 OCT 2026</p><h1>Native-size vegetation checks,<br>with the final choice left to you.</h1>
<p class="lead">Landed: Annotate → Check vegetation pattern → Check this mark. See the matching ink and choose “Use Other — not saved,” then save when ready.</p>
<section><h2>What supports this landing?</h2><table><tr><th>Evaluation</th><th>Vegetation suggestions</th><th>Other suggestions</th><th>Decision</th></tr><tr><td>V1 reused development · 252 crops</td><td>7 / 49 vegetation-like</td><td>0</td><td>Test fresh</td></tr><tr><td>V1 fresh spatial check · 44 crops</td><td>10</td><td>2: ambiguous loop, digit 9</td><td>Reject V1</td></tr><tr><td>V2 reused development · 296 crops</td><td>16 / 62 vegetation-like</td><td>0</td><td>Test fresh again</td></tr><tr><td>V2 new-pixel check · 36 crops</td><td>15</td><td>0; one geometry match vetoed as numeric</td><td>Advisory only</td></tr></table>
<p>The final 36 contain 15 vegetation-like marks, 10 POIs, 2 numeric labels, 6 noises and 3 uncertain marks. The sample deliberately includes 16 geometry matches and 20 controls, so 15/15 is <strong>not a recall or real-world precision estimate</strong>. Two earlier failures are no longer called fresh evidence after correction.</p>
<p>Both map editions are represented. New crops do not overlap earlier evidence, including the 64px number-reader context, but nearby areas and printing styles recur. Labels are assistant visual judgments made with predictions hidden; they are not independently verified human ground truth. Automatic filtering is not supported.</p></section>
<section><h2>Shape, size, ownership, number context</h2><p>The check uses original z16 pixels. A small ring must belong to one compact ink component with a downward stem, occupy enough of the detection box, and persist at two of three ink thresholds. A small morphological opening separates some thin contour connections. It does not resize every symbol to a common size.</p><p>Control 9 (hot spring), 8 (school) and 7 (height label) receive no suggestion. 33495 remains known noise without a vegetation hit: generic noise is a different problem. No runtime names, manual annotations, OSM matches or evaluation labels feed this method.</p><p>The first trial mistook a digit 9 and a tiny square loop for vegetation. Raising only the minimum component height removes the tiny loop 53137. The overlapping multi-digit OCR veto then removes 44253, and independently blocks 100885 in the new check. OCR need not read the number correctly to prevent a vegetation suggestion: “0988” was wrong as a transcription but useful as a veto.</p><p>The ownership check also retains POI 95054, whose large text box happens to contain vegetation at its edge. An asymmetric lower-stem check excludes loop-like noise 17117. These are reused diagnostic cases, not fresh accuracy evidence.</p></section>
<section><h2>The editor behavior</h2><img class="wide" src="editor-preview.png" alt="Live Mapwalker editor displaying original pixels, orange detection box, green symbol box and Other selected as a draft"><p>Only an explicit button click changes the draft type. The name, OSM link, notes, grouping and visibility are preserved. Missing or changed imagery, an unavailable reader or a busy reader produce no suggestion. A late response cannot alter another POI. No saved annotation was changed during live verification.</p></section>
<section><h2>Every geometry-positive crop from the new check</h2><div class="cards">{cards}</div><p><a href="fresh-v2/sheet-0.jpg">Blind sheet 1</a> · <a href="fresh-v2/sheet-1.jpg">Blind sheet 2</a> · <a href="fresh-v2/dataset.json">All 36 predictions and original pixel hashes</a> · <a href="fresh-v2/visual-labels.json">Visual references</a> · <a href="fresh-v2/selection.json">Selection rules</a></p></section>
<section><h2>Cost and retained negatives</h2><p>Desktop CPU audit wall time (service plus frozen crop encoding/writing): geometry-positive median {ms['median']:.0f}ms, p95 {ms['p95']:.0f}ms, max {ms['maximum']:.0f}ms including one cold reader startup. No-match median {no['median']:.0f}ms. This is an on-demand check, not a background scan. Browser/network latency is excluded.</p><p>Early variants below use the same 252 reused crops. The detached-dot requirement drops useful hits; connected-component shape alone still needs ownership and numeric checks. Previously rejected repeated-pattern and HOG methods remain rejected; no unsupported automatic rule has been enabled.</p><div class="scroll"><table><tr><th>Early variant</th><th>Vegetation hits</th><th>Other hits</th></tr>{table}</table></div></section>
<section><h2>Reproduce and review</h2><p><a href="contract.md">Contract</a> · <a href="candidate-v2-lock.json">Frozen code hashes</a> · <a href="summary.json">Totals</a> · <a href="failure-ablations.json">Single-change failure probes</a> · <a href="timing-summary.json">Timing decomposition</a> · <a href="environment.json">Runtime and reader model hashes</a> · <a href="verification.json">Verification</a> · <a href="artifact-manifest.json">Artifact hashes</a></p><p>Run <code>tools/report_vegetation_components.py</code> in the pinned runtime to check hashes, replay all 36 full-service results and rebuild this report. Full early mask telemetry is losslessly compressed as JSON.gz, with uncompressed hashes in <a href="trial-summary.json">trial-summary.json</a>. Research harnesses are outside the production path.</p></section></main></html>''','utf-8')
    print(json.dumps(dict(summary=totals,timing=timing,ablations=ablations),indent=2))

if __name__=='__main__':main()
