"""Replay frozen contour trials, score held-out labels, and publish offline evidence."""
import html
import importlib.util
import json
import math
from pathlib import Path

import cv2
import numpy as np
from PIL import Image, ImageDraw, ImageOps

from .contour_frequency_trial import ROOT,sha,spectrum
from .contour_topology_trial import features,thin,graph_degree

FREQ=ROOT/'evidence/contour-frequency'
TOPO=ROOT/'evidence/contour-topology'
DATA=ROOT/'evidence/contour-samples'


def read(path):return json.loads(path.read_text(encoding='utf8'))


def write(path,data):path.write_text(json.dumps(data,ensure_ascii=False,indent=2)+'\n',encoding='utf8')


def heldout(folder,methods):
    labels=read(folder/'visual-labels.json');rows=read(folder/'predictions.json')
    negative=set(labels['contour_indices']);other=set(labels['uncertain_indices']+labels['vegetation_like_indices'])
    assert not negative&other and negative|other=={r['index'] for r in rows}
    summary={}
    for method in methods:
        hits=[r['index'] for r in rows if (r['rejected'][method] if isinstance(r['rejected'],dict) else r['rejected'])]
        summary[method]=dict(contour_hits=len(set(hits)&negative),contour_total=len(negative),
            protected_or_uncertain_hits=len(set(hits)&other),protected_or_uncertain_total=len(other),hit_indices=hits)
    write(folder/'summary.json',summary)
    return summary


def replay():
    samples=read(FREQ/'samples.json');frequency=read(FREQ/'results.json')
    topology=read(TOPO/'v2/predictions.json')
    # Replay the failed v1 with its exact source snapshot too.
    spec=importlib.util.spec_from_file_location('tools.contour_topology_v1',TOPO/'trial-v1.py')
    v1=importlib.util.module_from_spec(spec);spec.loader.exec_module(v1)
    original=read(TOPO/'predictions.json')
    assert sha(TOPO/'trial-v1.py')==read(TOPO/'lock.json')['code_sha256']
    assert sha(ROOT/'tools/contour_topology_trial.py')==read(TOPO/'v2/lock.json')['code_sha256']
    for row,fr,t1,t2 in zip(samples,frequency,original,topology):
        assert row['id']==fr['id']==t1['id']==t2['id']
        assert sha(ROOT/row['context'])==row['context_sha256']
        with Image.open(ROOT/row['context']) as im:context=im.convert('RGB')
        if 'mark' in row:
            assert sha(ROOT/row['mark'])==row['mark_sha256']
            with Image.open(ROOT/row['mark']) as im:mark=im.convert('RGB')
        else:
            a,b,c,d=row['context_box'];mark=context.crop((math.floor(a)-4,math.floor(b)-4,math.ceil(c)+4,math.ceil(d)+4))
        assert spectrum(mark)==fr['features']['mark']
        assert spectrum(context)==fr['features']['context']
        assert v1.features(context,row['context_box'])==t1['features']
        assert features(context,row['context_box'])==t2['features']
    lock=read(FREQ/'reserved/lock.json')
    assert sha(ROOT/'tools/contour_frequency_trial.py')==lock['trial_code_sha256']
    assert sha(DATA/'dataset.json')==lock['dataset_sha256']
    assert sha(FREQ/'reserved/predictions.json')==lock['predictions_sha256']
    dataset=read(DATA/'dataset.json');reserved={r['id']:r for r in dataset if r['split']=='reserved-evaluation'}
    for r in read(FREQ/'reserved/predictions.json'):
        for name in ('mark','context'):
            with Image.open(DATA/reserved[r['id']][name]) as im:assert spectrum(im)==r['features'][name]
    fresh=read(TOPO/'fresh/predictions.json');lock=read(TOPO/'fresh/lock.json')
    assert sha(TOPO/'fresh/predictions.json')==lock['predictions_sha256']
    assert sha(ROOT/'tools/contour_topology_trial.py')==lock['code_sha256']
    previous=[]
    for path,digest in lock['prior_hashes'].items():
        path=ROOT/path;assert sha(path)==digest
        rows=read(path);previous.extend(rows.get('scenes',[]) if isinstance(rows,dict) else rows)
    for row in fresh:
        assert sha(TOPO/'fresh'/row['crop'])==row['sha256']
        with Image.open(TOPO/'fresh'/row['crop']) as im:assert features(im,row['context_box'])==row['features']
        assert all(max(abs(row['x']-old['x']),abs(row['y']-old['y']))>=3 for old in previous if old.get('z')==16 and 'x' in old)
    for r in dataset:
        for name in ('mark','context'):assert sha(DATA/r[name])==r[name+'_sha256']
    dev=[r for r in dataset if r['split']=='development'];res=list(reserved.values())
    assert not {r['block'] for r in dev}&{r['block'] for r in res}
    assert len({(r['x'],r['y']) for r in dataset})==len(dataset)
    for a in dev:
        for b in res:
            assert max(abs(a['x']-b['x']),abs(a['y']-b['y']))>=3
            assert not {(p['z'],p['x'],p['y']) for p in a['sources']} & {(p['z'],p['x'],p['y']) for p in b['sources']}
    stats={}
    for name,rows in [('frequency',frequency),('topology-v1',original),('topology-v2',topology)]:
        times=[r['feature_ms'] for r in rows]
        stats[name]=dict(zip(['median','p95','maximum'],map(float,np.percentile(times,[50,95,100]))))
    result=dict(status='PASS',development_rows_replayed=len(samples),frequency_reserved_replayed=len(reserved),
        topology_fresh_replayed=len(fresh),native_sample_hashes_verified=426,
        spatial_checks='Dataset splits: no shared blocks or source tiles, >=3 tile-index distance; fresh topology contexts >=3 from all named previous contexts.',
        feature_latency_ms=stats,latency_scope='Original single run, excludes crop decoding/I/O; unoptimized Python on this host. Not a production speed guarantee.',
        python=__import__('sys').version,opencv=cv2.__version__,numpy=np.__version__)
    write(TOPO/'verification.json',result)
    return result


def figure():
    rows={r['id']:r for r in read(FREQ/'samples.json')}
    examples=[('21397','Frequency: contour hit'),('33104','Topology + parallel: contour hit'),
              ('45553','Parallel alone: protected POI flagged'),('45400','Graph alone: text flagged')]
    board=Image.new('RGB',(1056,660),'white');draw=ImageDraw.Draw(board)
    for n,(identity,title) in enumerate(examples):
        row=rows[identity];x=(n%2)*528;y=(n//2)*330
        with Image.open(ROOT/row['context']) as im:im=im.convert('RGB')
        gray=np.asarray(im.convert('L'),dtype=np.float32)/255
        skel=thin((cv2.GaussianBlur(gray,(0,0),8)-gray)>18/255)
        graph=np.full((*skel.shape,3),255,dtype=np.uint8);graph[skel]=[35,85,170]
        graph[skel & (graph_degree(skel)>=3)]=[200,40,40]
        overlay=Image.fromarray(graph)
        for pic in (im,overlay):ImageDraw.Draw(pic).rectangle(row['context_box'],outline='red',width=1)
        draw.text((x+8,y+6),title,fill='black')
        draw.text((x+8,y+24),f'POI {identity}; review label: {row["label"]}',fill='black')
        board.paste(ImageOps.contain(im,(248,248),Image.Resampling.NEAREST),(x+8,y+48))
        board.paste(ImageOps.contain(overlay,(248,248),Image.Resampling.NEAREST),(x+272,y+48))
        draw.text((x+8,y+304),'Original target + context',fill='black')
        draw.text((x+272,y+304),'Skeleton; red points = branches',fill='black')
    board.save(TOPO/'examples.png')


def main():
    verify=replay()
    freqheld=heldout(FREQ/'reserved',['mark','context','joint'])
    topoheld=heldout(TOPO/'fresh',['topology_and_parallel'])
    figure()
    fs=read(FREQ/'summary.json');ts=read(TOPO/'v2/summary.json')
    table=''
    for title,row,fresh,decision in [
        ('Frequency concentration on target',fs['mark'],freqheld['mark'],'Retain as a limited feature; insufficient evidence for automatic hiding'),
        ('Frequency concentration on context',fs['context'],freqheld['context'],'No fresh contour hits; do not enable'),
        ('Frequency target AND context',fs['joint'],None,'Reject: zero development hits'),
        ('Parallel local directions',ts['parallel'],None,'Reject: flags one protected POI and two uncertain marks'),
        ('Graph continuation',ts['graph'],None,'Reject: flags text, vegetation and an uncertain mark'),
        ('Graph continuation AND parallel neighbors',ts['topology_and_parallel'],topoheld['topology_and_parallel'],'Retain hypothesis only: no fresh hits; do not enable')]:
        freshtext=(f"{fresh['contour_hits']}/{fresh['contour_total']} contours; {fresh['protected_or_uncertain_hits']}/{fresh['protected_or_uncertain_total']} other flags" if fresh else 'Stopped before held-out test')
        table+=f"<tr><td>{title}</td><td>{row['contour_hits']}/138</td><td>{row['protected_or_uncertain_hits']}/112</td><td>{freshtext}</td><td>{decision}</td></tr>"
    page=f'''<!doctype html><html lang="en"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>Contour noise: frequency and topology trials</title>
<style>body{{max-width:1150px;margin:24px auto;padding:0 18px;font:17px/1.6 system-ui;color:#203b32;background:#fafaf5}}a{{color:#24684d}}img{{max-width:100%;height:auto}}table{{border-collapse:collapse;min-width:780px}}td,th{{text-align:left;vertical-align:top;padding:12px;border-bottom:1px solid #ccd4c8}}.scroll{{overflow:auto}}.notice{{background:#edf0df;padding:18px}}</style>
<a href="/">Back to map</a> · <a href="../contour-samples/report.html">Collected samples</a><h1>Contour structure helps, but simple rules miss most noise</h1><p>3 October 2026 · Offline evidence; no detector, database, ranking or viewer behavior changed.</p>
<p class="notice">Collected <strong>138 visually labelled contour negatives</strong>, including <strong>86 passing the current Top threshold</strong>. The frequency rule found 8 in development and 1 in a separate 13-contour evaluation. The topology + parallel rule found 3 in development and none of 7 fresh contours. Neither supports broad automatic removal.</p>
<h2>Measured gain and risk</h2><div class="scroll"><table><tr><th>Candidate</th><th>Development contour hits</th><th>Protected / uncertain flags</th><th>Separate evaluation</th><th>Decision</th></tr>{table}</table></div>
<p>The two held-out columns use different sample sets: frequency has 21 contexts (13 contours, 8 uncertain/vegetation marks); topology has 23 newly collected contexts (7 contours, 16 uncertain/vegetation marks). Predictions were saved before viewing either set. No thresholds were tuned on these labels. These sets are now consumed, not future holdouts.</p>
<h2>What the tests measure</h2><p>Frequency concentration uses native pixels, a Hann window and energy at wavelengths 4–64 pixels. It requires at least 70% of energy near one axis, or 90% near two separated axes. Small target crops under 12 pixels on either side abstain. The limited successes support the user's observation about simple directional contour fragments; the results do not establish a general contour detector.</p>
<p>The topology pilot skeletonizes locally dark ink. It requires most target ink to belong to a component extending well beyond the target, no interior endpoints, very few branch pixels, and three separate long neighboring components. Local image-gradient directions then test parallel alignment. This approximates continuation and parallel neighbors; it does not trace a full family of curves or verify equal curvature and spacing point by point. Tight bends, faint broken printing and merged ink remain difficult.</p>
<p>The first topology implementation incorrectly counted redundant diagonal pixel connections at ordinary bends as branches. A synthetic elbow exposed the error. The corrected graph preserves real T-junctions and closed loops; the original result and exact source are retained. Original graph/combined gates: 0 contour hits. Corrected graph: 10 hits but 3 protected/uncertain flags. Corrected combined gate: 3 hits, no flags in the development probes.</p>
<h2>Examples and counterexamples</h2><a href="examples.png"><img src="examples.png" alt="Two contour hits and two protected targets incorrectly flagged by individual features, alongside their skeleton graphs"></a>
<p>A protected mark can touch a long contour and enter the same connected component. A nearby line family can also dominate orientation around a real mark. Both failures argue for explaining the target's actual ink, including any residual strokes or loops, before treating it as a contour fragment. Tightening a global score is not supported by these experiments.</p>
<h2>Reference quality and limits</h2><p>The 192 development contexts contain 138 contour targets, 18 text/number targets and 36 uncertain or other marks. Another 58 previously reviewed text, numbers, POIs and rare-symbol controls are reused protection probes, giving 112 total non-contour guards. All new visual labels are assistant assessments, not independent ground truth. Labels apply only inside the target box: other marks in the context are not labelled noise.</p>
<p>Collection is enriched for detector mistakes and excludes some geographic areas. These counts are not population precision/recall. Neither fresh set supplies confirmed readable names/numerals; zero observed guard flags is insufficient to claim safety. Known hot-spring and other rare-symbol probes remain protected in the tested combined rules but are reused examples. Reserved geography excludes named previous studies, not every possible prior exposure.</p>
<h2>Verification and next method</h2><p>Replayed all 250 development/protection inputs through frequency and both graph versions, plus 21 frequency and 23 topology evaluation inputs. Verified 426 original crop hashes, locked prediction/source hashes and recorded spatial separation. Four graph regression cases cover bends, diagonals, real branches and loops. See <a href="verification.json">verification and latency</a>; timing excludes image decoding and I/O and is not a production performance claim.</p>
<p>The evidence supports using these measurements as inputs to a target-level classifier, with contour training crops and protected marks mixed into the same training process. A stronger topology candidate should trace neighboring curves, compare their local bends, and test what target ink remains unexplained by those curves. It must then pass a new, independently checked set of names, numbers, Kana and rare symbols before automatic viewer suppression.</p>
<p><a href="../contour-samples/training.json">Training manifest</a> · <a href="../contour-frequency/parameters.json">Frequency parameters</a> · <a href="v2/parameters.json">Topology parameters</a> · <a href="v2/summary.json">Development results</a> · <a href="fresh/summary.json">Fresh results</a> · <a href="fresh/visual-labels.json">Fresh visual labels</a></p>
<h2>Fresh topology contact sheets</h2><a href="fresh/sheet-0.jpg"><img loading="lazy" src="fresh/sheet-0.jpg" alt="Fresh topology examples 1–12"></a><a href="fresh/sheet-1.jpg"><img loading="lazy" src="fresh/sheet-1.jpg" alt="Fresh topology examples 13–23"></a></html>'''
    (TOPO/'report.html').write_text(page,encoding='utf8')
    (FREQ/'report.html').write_text('<!doctype html><html lang="en"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>Contour frequency results</title><h1>Contour frequency results</h1><p>Target frequency concentration: 8/138 development contour hits, 0/112 protected or uncertain flags. Reserved evaluation: 1/13 contour hits, 0/8 other flags.</p><p><a href="../contour-topology/report.html">Full frequency and topology comparison, examples and limitations</a></p></html>',encoding='utf8')
    samplepage=(DATA/'report.html').read_text(encoding='utf8')
    notice='<p class="notice" id="later-evaluation">Later evaluation: the original 21 reserved samples have now been inspected for the frequency trial and are no longer fresh. See the <a href="../contour-topology/report.html">frequency and topology results</a>. Earlier statements below describe the collection-stage status.</p>'
    if 'id="later-evaluation"' not in samplepage:
        samplepage=samplepage.replace('<h1>Contour fragments are abundant</h1>','<h1>Contour fragments are abundant</h1>'+notice)
        (DATA/'report.html').write_text(samplepage,encoding='utf8')
    groups={DATA:['mine_contour_samples.py','package_contour_samples.py'],
            FREQ:['contour_frequency_trial.py','contour_frequency_holdout.py'],
            TOPO:['contour_topology_trial.py','contour_topology_holdout.py','report_contour_trials.py']}
    for folder,names in groups.items():
        files=[p for p in folder.rglob('*') if p.is_file() and p.name!='artifact-manifest.json' and '__pycache__' not in p.parts]
        files += [ROOT/'tools'/name for name in names]
        if folder==TOPO:files.append(ROOT/'tests/test_contour_topology_trial.py')
        write(folder/'artifact-manifest.json',{p.relative_to(ROOT).as_posix():sha(p) for p in sorted(files)})
    print(json.dumps(dict(verification=verify,frequency_reserved=freqheld,topology_fresh=topoheld),indent=2))


if __name__=='__main__':main()
