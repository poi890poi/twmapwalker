"""Score frozen outputs, never provide labels to inference."""
import hashlib
import html
import json
import re
import statistics
import sys
from pathlib import Path

from PIL import Image

ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from mapwalker.reading_suggestions import overlaps,unrotate_box
OUT=ROOT/'evidence/reading-improvements'


def load(name):return json.loads((OUT/name).read_text('utf-8'))
def stats(values):
    values=sorted(values)
    return dict(median=round(statistics.median(values),1),p95=round(values[min(len(values)-1,int(len(values)*.95))],1),maximum=round(max(values),1))


def main():
    labels=load('labels.json');samples={s['id']:s for s in load('inputs.json')}
    numeric=[k for k,v in labels.items() if not k.startswith('ref-') and re.fullmatch(r'\d+(?:[.,]\d+)?',v.get('ground_truth',''))]
    names=[k for k,v in labels.items() if not k.startswith('ref-') and v.get('ground_truth') and k not in numeric]
    noise=[k for k,v in labels.items() if v['classification']=='noise'];table=[];models={}
    for model in ('chinese','japanese','english','chinese-pad24','english-pad24','chinese-pad64-detect'):
        result=load(model+'.json');rows={r['id']:r for r in result['rows']};models[model]=rows
        any_exact=lambda keys:sum(any(v['text']==labels[k]['ground_truth'] for v in rows[k]['readings']) for k in keys)
        best_exact=sum(max(rows[k]['readings'],key=lambda r:r['score'],default={'text':''})['text']==labels[k]['ground_truth'] for k in numeric)
        table.append(dict(method=model,numeric_exact_any=any_exact(numeric),numeric_best=best_exact,full_name_exact_any=any_exact(names),
            noise_with_output=sum(any(v['text'] and v['score']>=.65 for v in rows[k]['readings']) for k in noise),
            kana_diagnostic=any_exact(['ref-0','ref-1','ref-2']),latency_ms=stats([r['ms'] for r in rows.values()]),model_sha256=result['model_sha256']))
    old=json.loads((ROOT/'evidence/multi-evidence/region-readings.json').read_text('utf-8'))
    oldrows={str(r['id']):r for r in old['rows']}
    table.append(dict(method='previous-detector-pad8',numeric_exact_any=sum(any(v['text']==labels[k]['ground_truth'] for v in oldrows[k]['readings']) for k in numeric),
        numeric_best=sum(max(oldrows[k]['readings'],key=lambda r:r['score'],default={'text':''})['text']==labels[k]['ground_truth'] for k in numeric),
        full_name_exact_any=sum(any(v['text']==labels[k]['ground_truth'] for v in oldrows[k]['readings']) for k in names),
        noise_with_output=sum(any(v['score']>=.65 for v in oldrows[k]['readings']) for k in noise),kana_diagnostic=None,
        latency_ms=stats([r['ms'] for r in oldrows.values()]),model_sha256=old['models']))
    policy={}
    for key,row in models['chinese-pad64-detect'].items():
        if key.startswith('ref-'):continue
        sample=samples[key];box=sample['box'];local=[64+box[0]-int(box[0]//1),64+box[1]-int(box[1]//1),64+box[2]-int(box[0]//1),64+box[3]-int(box[1]//1)]
        size=Image.open(OUT/f'{key}-pad64.png').size;seen=set();kept=[]
        for r in sorted(row['readings'],key=lambda r:r['score'],reverse=True):
            if (r['text'] not in seen and r['score']>=.65 and re.fullmatch(r'[0-9]{2,5}(?:[.,][0-9]+)?[.,]?',r['text'])
                    and overlaps(unrotate_box(r['box'],r['angle'],*size),local)):
                kept.append(r);seen.add(r['text'])
        policy[key]=kept[:8]
    exact=lambda key,r:r['text']==labels[key]['ground_truth']
    policy_summary=dict(exact_any=sum(any(exact(k,r) for r in policy[k]) for k in numeric),
                        exact_first=sum(bool(policy[k]) and exact(k,policy[k][0]) for k in numeric),
                        numeric_suggestions=sum(len(policy[k]) for k in numeric),
                        noise_findings_with_number_suggestion=sum(bool(policy[k]) for k in noise))
    kana_noise=sum(any(r['score']>=.65 and re.search(r'[\u3041-\u3096\u30a1-\u30fa]',r['text'])
                       for r in models['japanese'][k]['readings']) for k in noise)
    holdout=load('holdout-results.json');hl=load('holdout-labels.json')['labels'];hr={str(r['id']):r['results'] for r in holdout['results']}
    hn=[k for k,l in hl.items() if l['kind']=='number']
    hsummary=dict(number_findings=len(hn),exact_any=sum(any(r['text']==hl[k]['text'] for r in hr[k]['numbers']['readings']) for k in hn),
        exact_first=sum(bool(hr[k]['numbers']['readings']) and hr[k]['numbers']['readings'][0]['text']==hl[k]['text'] for k in hn),
        wrong_number_alternatives=sum(r['text']!=hl[k]['text'] for k in hn for r in hr[k]['numbers']['readings']),
        other_findings_with_output=sum(bool(hr[k][m]['readings']) for k in hl if k not in hn for m in ('numbers','kana')),
        number_ms=stats([r['numbers']['timing_ms']['recognition'] for r in hr.values()]),kana_ms=stats([r['kana']['timing_ms']['recognition'] for r in hr.values()]))
    result=dict(numeric_findings=len(numeric),name_findings=len(names),noise_findings=len(noise),comparison=table,
        number_tool=policy_summary,number_outputs=policy,kana_noise_findings_with_suggestion=kana_noise,holdout=hsummary,
        hashes={p.name:hashlib.sha256(p.read_bytes()).hexdigest() for p in [OUT/'inputs.json',OUT/'labels.json',OUT/'inputs-pad64.json',OUT/'holdout-inputs.json',Path(__file__)]})
    (OUT/'evaluation.json').write_text(json.dumps(result,ensure_ascii=False,indent=2),'utf-8')
    esc=html.escape
    rows=''.join(f'<tr><td>{r["method"]}</td><td>{r["numeric_exact_any"]}/17</td><td>{r["numeric_best"]}/17</td><td>{r["full_name_exact_any"]}/{len(names)}</td><td>{r["noise_with_output"]}/{len(noise)}</td><td>{r["kana_diagnostic"] if r["kana_diagnostic"] is not None else "—"}</td><td>{r["latency_ms"]["median"]}</td></tr>' for r in table)
    cards=''.join(f'<figure><img src="{key}-pad64.png" alt="Expanded automatic crop {key}"><figcaption>#{key} · saved reference {esc(labels[key]["ground_truth"])}<br>Suggestions: {esc(" / ".join(r["text"] for r in policy[key]) or "none")}</figcaption></figure>' for key in ('70070','70486','68891','17124','43947'))
    text=f'''<!doctype html><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>Names, numbers & Kana · Mapwalker</title>
<style>body{{font:16px/1.6 system-ui;background:#f5f5ed;color:#203a33;margin:auto;max-width:1100px;padding:24px}}h1{{font-size:36px}}a{{color:#286b5a}}table{{border-collapse:collapse;font-size:14px}}th,td{{border:1px solid #bbc9bc;padding:8px;text-align:left}}.table{{overflow:auto}}.cards{{display:flex;flex-wrap:wrap}}figure{{margin:12px;padding:14px;background:white;max-width:285px}}figure img{{max-width:100%;image-rendering:pixelated}}img.wide{{width:100%}}code{{overflow-wrap:anywhere}}</style>
<a href="/">← Mapwalker</a><h1>Names, numbers & Kana</h1><p>Candidate names now fill an editable draft. The editor also offers explicit number and Kana rereading. Nothing is automatically saved or promoted to a POI.</p>
<h2>What improved</h2><p>Re-detecting within 64 pixels of the automatic box recovers complete 1210 and 1059 readings. A fixed Japanese reader reads ウ・ラ・イ on all three manually cropped controls; Chinese reads none. These are useful editing aids, not validated whole-map detectors.</p>
<img class="wide" src="editor-preview.png" alt="Editor showing candidate name buttons and an unsaved draft">
<h2>Controlled comparison</h2><p>111 automatic crops plus eight manual controls. Same fixed images, four rotations per method. “Any” is an optimistic candidate-list metric, not a selected-answer accuracy. Scores are not calibrated across models. Full names often extend outside the automatic fragment.</p>
<div class="table"><table><tr><th>Method</th><th>Number exact, any</th><th>Number exact, highest score</th><th>Full name exact, any</th><th>Noise findings with ≥.65 output</th><th>Kana controls /3</th><th>Median ms/crop</th></tr>{rows}</table></div>
<p>The pad8 detector row reuses the previous frozen second-pass trial. Changing pad8 to pad64 holds its detector, upscaling and four rotations fixed. Recognition-only model swaps hold pad8 pixels fixed. Padding24 without detection is worse and rejected. English helps two numeric cases but makes confident errors; replacing the reader is rejected.</p>
<p>The Kana-only output filter still returns suggestions on {kana_noise}/{len(noise)} noise-labeled findings. No tested reader recovers an entire manually named label from these automatic fragments. The Japanese option is therefore an explicit editing aid, with no automatic background integration. Bigger-name grouping remains unresolved.</p>
<h2>The optional number tool</h2><p>Keep readings at score ≥.65 only when their boxes overlap the selected fragment; preserve exact digits and punctuation. Retain competing rotations. On the 17 labeled number findings: {policy_summary['exact_any']} contain an exact reference reading, {policy_summary['exact_first']} have it first; {policy_summary['noise_findings_with_number_suggestion']} of {len(noise)} noise-labeled findings produce a number suggestion. Partial numeric references and punctuation differences make strict exact matching conservative. Decimal marks are never silently stripped.</p><div class="cards">{cards}</div>
<h2>Fresh post-proposal check</h2><p>Twelve additional existing detections were selected by a fixed hash ordering, frozen, and run before viewing. Six already had numeric OCR; six were unread small regions. This selects a narrow sample and is not a whole-map recall estimate. Visual references below were assigned afterward by the assistant. Duplicate detections may describe the same number.</p>
<p>Number tool: {hsummary['exact_any']}/6 contain the visible number, {hsummary['exact_first']}/6 have it first. There are {hsummary['wrong_number_alternatives']} wrong numeric alternatives, including upside-down “001” alongside “1100”. All six unread controls return no suggestions in either mode. No Kana occurs in this fresh check, so Kana generalization remains unmeasured.</p>
<p>A live check found that the Kana API rounded the bottom edge outward while the frozen recognition trial truncated it. One added pixel row changed モ from score .675 to .521. The API now preserves the tested pixels. A <a href="kana-policy-replay.json">post-fix replay</a> (not a fresh holdout) retains no outputs on the six unread controls, but adds a wrong “1で9” alternative on the numeric 651 crop. This negative result is retained; the score threshold was not weakened.</p>
<img class="wide" src="holdout-contact.png" alt="Twelve frozen additional map crops with automatic detection boxes">
<p>Warm recognition latency on this check, median/p95/max: numbers {hsummary['number_ms']}; Kana {hsummary['kana_ms']}. Input decode and model initialization are recorded separately. Cache hits are not counted as fresh inference.</p>
<h2>Scope and reproduction</h2><p>Models use only cached map pixels and automatic boxes. Manual labels, OSM names, modern coordinates and terrain never enter these readers. Recognition cannot decide peak versus contour. No detector jobs, fingerprints, ranks, filters, links or annotations are rewritten. Kana only returns unverified partial readings after an explicit click.</p>
<p>Optional Japanese weights: <a href="https://github.com/RapidAI/RapidOCR/blob/main/python/rapidocr/default_models.yaml">RapidAI model registry</a>, PP-OCRv4 Japanese mobile. SHA256 <code>e1075a67dba758ecfc7ebc78a10ae61c95ac8fb66a9c86fab5541e33f085cb7a</code>. Install with <code>python tools/install_reading_models.py</code>. Existing Chinese runtime dependencies are unchanged.</p>
<p><a href="evaluation.json">All metrics and per-finding number alternatives</a> · <a href="contract.json">Contract</a> · <a href="holdout-results.json">Fresh raw outputs and timings</a> · <a href="holdout-labels.json">Visual references</a>. Reproduce with <code>tools/trial_map_readings.py</code>, <code>tools/reading_holdout.py</code>, then <code>tools/report_reading_improvements.py</code>. Frozen pixel and model hashes accompany every run.</p>'''
    (OUT/'report.html').write_text(text,'utf-8');print(json.dumps({'number_tool':policy_summary,'holdout':hsummary,'comparison':table},ensure_ascii=False,indent=2))


if __name__=='__main__':main()
