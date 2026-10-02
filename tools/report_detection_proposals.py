"""Evaluate locked outputs and publish their gains, failures and limits."""
import hashlib
import html
import json
import math
import platform
import re
import statistics
import subprocess
import sys
from collections import Counter
from pathlib import Path
from PIL import Image
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from tools.run_detection_proposals import load,save,sha,OUT,PARAMETERS
from mapwalker.reading_suggestions import overlaps,unrotate_box

def stats(values):
    v=sorted(values)
    return dict(n=len(v),mean=round(statistics.mean(v),2),median=round(statistics.median(v),2),p95=round(v[min(len(v)-1,int(.95*len(v)))],2),maximum=round(max(v),2)) if v else None
def unique(rows):
    seen=set();kept=[]
    for r in sorted(rows,key=lambda r:-r['score']):
        if r['text'] not in seen:kept.append(r);seen.add(r['text'])
    return kept
def policies(rows):
    angles={v['text']:{r['angle'] for r in rows if r['text']==v['text']} for v in rows}
    return {'all-rotations':unique(rows),'upright-only':unique([r for r in rows if r['angle']==0]),'two-rotation-agreement':unique([r for r in rows if len(angles[r['text']])>=2])}
def numeric_metrics(rows,refs):
    result={}
    for pad in ('8','64'):
        for policy in ('all-rotations','upright-only','two-rotation-agreement'):
            samples=[]
            for row in rows:
                if row['id'] not in refs:continue
                ref=refs[row['id']];values=policies(row['numbers'][pad])[policy]
                samples.append(dict(id=row['id'],reference=ref,readings=values,exact_any=any(v['text']==ref.get('text') for v in values),exact_first=bool(values) and values[0]['text']==ref.get('text')))
            positive=[s for s in samples if s['reference']['kind']=='number'];negative=[s for s in samples if s['reference']['kind']=='non-text']
            result[f'pad{pad}/{policy}']=dict(positive_total=len(positive),exact_any=sum(s['exact_any'] for s in positive),exact_first=sum(s['exact_first'] for s in positive),wrong_alternatives=sum(v['text']!=s['reference']['text'] for s in positive for v in s['readings']),
                abstained=sum(not s['readings'] for s in positive),negative_total=len(negative),negative_with_output=sum(bool(s['readings']) for s in negative),samples=samples)
    return result
def matched(a,b):
    inter=max(0,min(a[2],b[2])-max(a[0],b[0]))*max(0,min(a[3],b[3])-max(a[1],b[1]))
    aa=(a[2]-a[0])*(a[3]-a[1]);bb=(b[2]-b[0])*(b[3]-b[1])
    return inter/max(bb,1)>=.8 and inter/max(aa+bb-inter,1)>=.5

def main():
    refs=load(OUT/'visual-references.json');allruns={s:load(OUT/f'{s}-readings.json') for s in ('development','holdout','number-holdout')}
    geometry={};name_scores=[]
    for split in ('development','holdout'):
        scenes={s['id']:s for s in load(OUT/f'{split}-inputs.json')};geos=load(OUT/f'{split}-geometry.json');gs=[g for s in geos for g in s['groups']]
        identities={}
        for s in geos:
            scene=scenes[s['id']]
            for g in s['groups']:
                offset=[(scene['x']-1)*256,(scene['y']-1)*256]
                key=(scene['source'],tuple(sorted(tuple(round(v+offset[i%2],2) for i,v in enumerate(b)) for b in g['details']['member_boxes'])))
                identities[key]=refs['groups'][g['id']]['class']
        geometry[split]=dict(scenes=len(scenes),stored_proposal_instances=sum(len(s['proposals']) for s in scenes.values()),added_groups=len(gs),classes=dict(Counter(refs['groups'][g['id']]['class'] for g in gs)),unique_exact_member_sets=len(identities),unique_classes=dict(Counter(identities.values())),latency_ms=stats([s['ms'] for s in geos]))
        for ref in [r for r in refs['name_boxes'] if r['scene'] in scenes]:
            ps=scenes[ref['scene']]['proposals'];new=next(s['groups'] for s in geos if s['id']==ref['scene'])
            row=dict(**ref,baseline_envelope=any(matched(p['box'],ref['box']) for p in ps),with_groups_envelope=any(matched(p['box'],ref['box']) for p in ps+new),
                raw_exact=any(ref['text'] in [p.get('text','')]+[v.get('text','') for v in p['details'].get('reading_candidates',[])] for p in ps),group_reading={})
            for m in ('chinese','japanese'):
                row['group_reading'][m]=any(v['text']==ref['text'] and v['score']>=.65 for r in allruns[split]['rows'] if r['kind']=='group' and r['scene']==ref['scene'] for v in r['models'][m]['readings'])
            name_scores.append(row)
    fresh_numbers=numeric_metrics(allruns['number-holdout']['rows'],refs['number_holdout'])
    reading=ROOT/'evidence/reading-improvements';oldlabels=load(reading/'labels.json');oldinputs={r['id']:r for r in load(reading/'inputs.json')}
    oldrefs={k:dict(kind='number',text=v['ground_truth']) for k,v in oldlabels.items() if not k.startswith('ref-') and re.fullmatch(r'\d+(?:[.,]\d+)?',v.get('ground_truth',''))}
    oldrefs.update({k:dict(kind='non-text') for k,v in oldlabels.items() if v['classification']=='noise'})
    oldrows={k:dict(id=k,numbers={}) for k in oldrefs}
    for pad,path in [(8,ROOT/'evidence/multi-evidence/region-readings.json'),(64,reading/'chinese-pad64-detect.json')]:
        for r in load(path)['rows']:
            key=str(r['id'])
            if key not in oldrefs:continue
            b=oldinputs[key]['box'];local=[pad+b[0]-math.floor(b[0]),pad+b[1]-math.floor(b[1]),pad+b[2]-math.floor(b[0]),pad+b[3]-math.floor(b[1])]
            size=Image.open(reading/(key+('-pad64' if pad==64 else '')+'.png')).size
            oldrows[key]['numbers'][str(pad)]=[v for v in r['readings'] if v['score']>=.65 and re.fullmatch(PARAMETERS['number_pattern'],v['text']) and overlaps(unrotate_box(v['box'],v['angle'],*size),local)]
    oldnumeric=numeric_metrics(list(oldrows.values()),oldrefs)
    kana={}
    for model in ('chinese','japanese'):
        controls=[]
        for r in allruns['development']['rows']:
            if r['id'] not in refs['automatic_kana_controls']:continue
            expected=refs['automatic_kana_controls'][r['id']];vals=[v for v in r['models'][model] if v['score']>=.65]
            controls.append(dict(id=r['id'],reference=expected,readings=vals,exact=any(v['text']==expected for v in vals)))
        negatives=[r for r in allruns['holdout']['rows'] if refs['fresh_regions'].get(r['id'])=='non-text']
        kana[model]=dict(controls=controls,controls_total=len(controls),exact=sum(c['exact'] for c in controls),kana_controls_total=sum(c['reference']!='社' for c in controls),kana_exact=sum(c['exact'] and c['reference']!='社' for c in controls),
            fresh_nontext_total=len(negatives),fresh_nontext_any_output=sum(any(v['score']>=.65 and v['text'] for v in r['models'][model]) for r in negatives),
            fresh_nontext_kana_output=sum(any(v['score']>=.65 and re.search(r'[\u3041-\u3096\u30a1-\u30fa]',v['text']) for v in r['models'][model]) for r in negatives))
    timing={s:{k:stats([r['ms'][k] for r in run['rows'] if r['kind']=='automatic']) for k in ('chinese','japanese','number8','number64')} for s,run in allruns.items()}
    er=load(OUT/'evidence-ranking.json');rings=load(OUT/'rings.json')
    shifts={m:dict(n=len(rs:=[r for r in er['shifts'] if r['metres']==m]),top1=sum(r['rank']==1 for r in rs),top3=sum(r['rank'] is not None and r['rank']<=3 for r in rs),absent_from_returned_osm_list=sum(r['rank'] is None for r in rs)) for m in (250,500,1000)}
    result=dict(geometry=geometry,name_scores=name_scores,numbers_development=oldnumeric,numbers_fresh=fresh_numbers,kana=kana,ranking=er['summary'],shift_sensitivity=shifts,rings=rings['counts'],timing_ms=timing,
        decisions={'grouping':'Retain as research/manual proposal. Reject automatic merging: partial characters and false groupings persist; no fresh feature-name recovery.',
            'number-context':'Retain optional editing aid. Fresh exact-any gains, but wrong and inverted candidates remain; no automatic label replacement.',
            'upright-selection':'Retain for another orientation-stratified holdout; positive fresh result is small and upright-only loses development readings.',
            'rotation-agreement':'Reject mandatory gate: throws away correct candidates; same recognizer rotations are correlated, not independent evidence.',
            'japanese':'Retain explicit supplemental reader; reject replacement/background auto-naming. Fresh false Kana suggestions and small-tsu error.',
            'ranking-enrichment':'No measured saved-link gain. Do not expand background policy on this evidence.',
            'ring-context':'Reject automatic suppression. Protected POI losses exceed vegetation-like hits.'},
        environment=dict(python=sys.version,platform=platform.platform(),head=subprocess.check_output(['git','rev-parse','HEAD'],cwd=ROOT,text=True).strip()),
        provenance={str(p.relative_to(ROOT)):sha(p) for p in [OUT/'parameters.json',OUT/'visual-references.json',OUT/'sampling-addendum.json',reading/'labels.json',ROOT/'evidence/multi-evidence/region-readings.json',reading/'chinese-pad64-detect.json',Path(__file__)]})
    save(OUT/'evaluation.json',result)
    esc=html.escape
    def tab(headers,rows):return '<div class="scroll"><table><thead><tr>'+''.join('<th>'+esc(str(h))+'</th>' for h in headers)+'</tr></thead><tbody>'+''.join('<tr>'+''.join('<td>'+esc(str(v))+'</td>' for v in row)+'</tr>' for row in rows)+'</tbody></table></div>'
    def nums(data):return tab(['Method','Exact anywhere','Exact first','Wrong alternatives','No suggestion'],[(k,f"{v['exact_any']}/{v['positive_total']}",f"{v['exact_first']}/{v['positive_total']}",v['wrong_alternatives'],v['abstained']) for k,v in data.items()])
    def pic(path,caption):return f'<figure><a href="{path}"><img loading="lazy" src="{path}" alt="{esc(caption)}"></a><figcaption>{esc(caption)}</figcaption></figure>'
    summary_rows=[('Whole-label geometry','2 complete names; 1 more box covers a name but omits small ッ','9/17 development groups join unrelated marks; fresh: 0 feature-name groups','Research only'),('Expanded number context','Fresh exact reading available: 1/6 → 4/6','4 wrong alternatives; highest-score answer right on only 3/6','Optional editing aid'),('Japanese alongside Chinese','5/11 Kana glyph findings exact versus 0/11','2/10 fresh non-text findings get false Kana; ッ read as ツ','Explicit supplemental reader'),('Extra readings in evidence ranking','No saved-link gain: top-1 stays 4/12, top-3 8/12','Small reused link sample; zero gain is not proof of no future benefit','No automatic expansion'),('Repeated-ring filtering','2/17 vegetation-like findings caught','Would remove 7/23 saved POI findings and 2/10 protected controls','Reject suppression')]
    geomtable=tab(['Split','Stored boxes (instances)','Added groups','Class counts'],[(s,g['stored_proposal_instances'],g['added_groups'],'; '.join(f'{n} {k}' for k,n in g['classes'].items())) for s,g in geometry.items()])
    yes=lambda v:'Yes' if v else 'No'
    nametable=tab(['Reference','Baseline box covers whole label','With groups','Chinese exact group reading','Japanese exact group reading'],[(r['text'],yes(r['baseline_envelope']),yes(r['with_groups_envelope']),yes(r['group_reading']['chinese']),yes(r['group_reading']['japanese'])) for r in name_scores])
    numcases=tab(['Finding','Visual reference','pad8 alternatives','pad64 alternatives'],[(s['id'],s['reference'].get('text',s['reference']['kind']),' / '.join(v['text'] for v in next(t for t in fresh_numbers['pad8/all-rotations']['samples'] if t['id']==s['id'])['readings']) or 'none',' / '.join(v['text'] for v in s['readings']) or 'none') for s in fresh_numbers['pad64/all-rotations']['samples']])
    katable=tab(['Reader','Exact Kana glyph findings','Non-text with any ≥.65 reading','Non-text with Kana suggestion'],[(m,f"{v['kana_exact']}/{v['kana_controls_total']}",f"{v['fresh_nontext_any_output']}/{v['fresh_nontext_total']}",f"{v['fresh_nontext_kana_output']}/{v['fresh_nontext_total']}") for m,v in kana.items()])
    ranktable=tab(['Variant','Added readings on findings','Saved link top 1','Saved link top 3','Noise with support'],[(s,v['added_to'],f"{v['top1']}/12",f"{v['top3']}/12",f"{v['noise_supported']}/46") for s,v in er['summary'].items()])
    ringtable=tab(['Evaluation class','Findings','Ring alone','Ring with ≥3 neighbors within 80 px'],[(k,v['total'],v['ring_only'],v['repeated']) for k,v in rings['counts'].items()])
    timingtable=tab(['Split / method','N','Mean ms','Median ms','p95 ms','Max ms'],[(s+' / '+k,v['n'],v['mean'],v['median'],v['p95'],v['maximum']) for s,ts in timing.items() for k,v in ts.items()])
    doc='''<!doctype html><html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>Detection proposals: gain and risk evidence</title><style>
body{font:16px/1.6 system-ui,sans-serif;max-width:1180px;margin:auto;padding:24px;background:#f5f4ec;color:#183d35}h1{font-size:clamp(28px,5vw,46px);line-height:1.15}h2{margin-top:2em}a{color:#126651}.lead{font-size:20px}.badge{background:#dae8d7;padding:10px 15px;border-radius:8px}table{border-collapse:collapse;background:white;width:100%;font-size:14px}th,td{border:1px solid #bfccb9;padding:9px;text-align:left;vertical-align:top}th{background:#e5ecd9}.scroll{overflow:auto}.cards{display:grid;grid-template-columns:repeat(auto-fit,minmax(min(100%,300px),1fr));gap:16px}figure{margin:0;padding:12px;background:white;border-radius:8px}img{max-width:100%;height:auto}figcaption{font-size:14px;padding:8px 0}code{overflow-wrap:anywhere}details{margin:18px 0}summary{cursor:pointer;font-weight:600}.note{border-left:4px solid #a66c3a;padding-left:16px}</style></head><body>
<a href="/">← Mapwalker</a><h1>Detection proposals: measured gains and risks</h1><p class="lead">The most defensible gains are editing suggestions. None of these tests supports automatic name replacement, fragment merging, or hollow-dot suppression.</p><p class="badge">Offline experiment · 9 development scenes + 8 fresh spatial scenes + 8 separately sampled number scenes · methods locked before fresh inspection · production detection unchanged</p>'''
    doc+=tab(['Proposal','Observed gain','Observed risk or limit','Decision'],summary_rows)
    doc+='<h2>1. Whole-label grouping</h2><p>The existing fixed geometry prototype saw automatic boxes and scores only. It added 17 development groups to 342 stored box instances. Two groups contain every glyph of a complete name; a third encloses モッコ山 but omits the small ッ from its member list. This distinction matters: a good-looking rectangle does not prove correct character grouping.</p>'+geomtable+nametable
    doc+='<p>Only 内茅埔山 is recovered as a complete exact group reading at ≥.65, using Chinese. Japanese reads the grouped ウライ社 as ウライ武 at low confidence. The six fresh groups contain four marginal sheet inscriptions and two incorrect merges; none is a recovered feature-name group. Marginal text is real text, but it is not evidence of a mapped POI.</p><p>Instances overlap: exact member-set deduplication leaves '+str(geometry['development']['unique_exact_member_sets'])+' development groups and '+str(geometry['holdout']['unique_exact_member_sets'])+' fresh groups. Related partial groups still share places. These are not independent accuracy trials.</p><div class="cards">'+pic('development-20592-groups.png','Recovered complete four-character geometry: 内茅埔山.')+pic('development-wulai-groups.png','Correct ウライ社 geometry alongside an unrelated-symbol merge.')+pic('development-70070-groups.png','Failure: three separate contour labels joined into one group.')+pic('holdout-fresh-3-groups.png','Fresh failure: contour, middle name glyph and height joined together.')+'</div>'
    doc+='<h2>2. Numbers: more context versus orientation policy</h2><p>Same pixels, automatic box and reader; only padding changes from 8 to 64 pixels. Each expanded patch is re-detected at four rotations. Keep exact digits and punctuation at ≥.65 if the detected box overlaps the selected region. Both crop variants use identical floor rounding in this suite; the shipped number API uses ceil at the far edges, so these are not exact API replay claims.</p><h3>Fresh enriched sample</h3><p>Eight detections selected by hash from raw numeric OCR before viewing: six actual numbers and two contour/symbol false readings. Expanded context raises exact-any from 1/6 to 4/6, and exact-first from 1/6 to 3/6. Neither non-text case produces a number suggestion. The general spatial holdout contains no positive numeric owner regions and is kept separate.</p>'+nums(fresh_numbers)+numcases
    doc+='<p class="note">“66” scores .984 while the correct “7998” scores .859. The 686 crop returns upside-down “989.”. Confidence and rotation agreement are not correctness guarantees. Upright-only keeps all four exact fresh readings with no wrong alternatives, but this is only six positive cases. It loses correct development readings; do not replace the general policy from this result.</p>'+pic('number-holdout-review-0.png','All eight frozen numeric-cohort regions. Red boxes are automatic detections; references use surrounding pixels.')
    doc+='<details><summary>Previously labeled 17-number development replay and failures</summary><p>This reuses frozen reader outputs; it is not fresh inference. References include partial numbers and saved readings that may disagree with visible pixels. Strict transcript matching retains these limitations. The same score, numeric-pattern and overlap filters are applied before comparing selection policies. Punctuation is never normalized away.</p>'+nums(oldnumeric)+'</details>'
    doc+='<h2>3. Supplemental Japanese recognition</h2><p>Twelve manually assessed automatic glyph findings include eleven Kana and one 社. Chinese gets 社; Japanese recovers five Kana findings (four physical glyphs, because モ has two detector boxes). It misses the automatic ウ crop despite the earlier successful manual-crop diagnostic. It confidently changes small ッ into large ツ (.923), which strict full-name matching must count as an error.</p>'+katable
    doc+='<p>Fresh general-area owner regions: ten non-text, five marginal-text and one mixed-text finding. There are no positive Kana controls here. Japanese generates false く and ル suggestions on two non-text regions; Chinese produces no ≥.65 reading on those ten. This validates a failure mode, not positive Kana generalization. Keep Japanese as an explicit optional reader.</p>'+pic('holdout-review-0.png','All fresh owner regions and proposed groups. #99721 and #84269 produce false Kana suggestions.')
    doc+='<h2>4. Do extra readings improve modern-evidence matching?</h2><p>Replay the existing ranker on 111 frozen automatic regions with the same OSM snapshots, gazetteer and terrain. Append number readings or Japanese Kana readings in separate runs; preserve original OCR. Saved annotations and links are read only after inference for scoring. No grouped-reader combination is justified by the fresh grouping result.</p>'+ranktable
    doc+='<p>No saved-link rank improves in aggregate; no noise finding becomes supported on this 46-finding sample. This is a small reused evaluation set with 12 links to nine objects, not an independent geographic validation.</p><details><summary>Displacement sensitivity, not accuracy</summary>'+tab(['Artificial shift','Trials (12 links × 4 directions)','Top 1','Top 3','Absent from returned OSM candidates'],[(m,v['n'],v['top1'],v['top3'],v['absent_from_returned_osm_list']) for m,v in shifts.items()])+'<p>Shift historical coordinates by ±250/500/1000 m north/south/east/west while retaining the original candidate pool and 1 km radius. This isolates radius/rank sensitivity; it does not estimate true map drift, source coverage, or the best search radius. Missing rank also includes candidate-list truncation.</p></details>'
    doc+='<h2>5. Repeated hollow dots do not make a safe filter</h2><p>Keep the earlier ring-shape thresholds, then require at least three other detected rings within 80 native pixels. Deduplicate the same ring across thresholds. This sharply lowers vegetation-like hits and still rejects true POIs. Stop this suppression variant; do not tune it on the holdout.</p>'+ringtable
    protected=next((r['id'] for r in rings['rows'] if r['label']=='poi' and r['repeated']),None)
    if protected:doc+='<div class="cards">'+pic(f'ring-protected-{protected}.png','Protected POI that the repeated-ring rule would suppress. Red marks its automatic region.')+'</div>'
    doc+='<p>Legend research suggests many rings are vegetation symbols, while individual trees, survey symbols and numeric zeros require different treatment. These hypotheses do not turn “Other” into a reliable noise label. The 17 vegetation-like assessments are assistant interpretations, not independently verified ground truth. <a href="../hollow-dot/report.html">Previous legend evidence and rejected filters</a>.</p>'
    doc+='<h2>Timing and reproducibility</h2><p>CPU timings below cover fresh model calls only, including crop rotation and required reader preprocessing; image decoding and model initialization are outside these measurements. Groups have separate geometry/readout timings in JSON. These single runs are descriptive, not repeatable speedup claims. No cached API response is counted as fresh recognition.</p>'+timingtable
    doc+='<p>Fresh run initializations (seconds): '+esc(str({s:round(r['init_s'],2) for s,r in allruns.items()}))+'. Frozen prior-output replays have no fresh-inference latency claim. Static crops have no state continuity metric. No GPU or resident-memory benchmark was run.</p><h2>Scope and remaining evidence gaps</h2><p>Raw pixels, automatic geometry, fixed public OCR weights and frozen public evidence are the inference inputs. Names, classes, links and hand-drawn boxes are evaluation-only. Methods were fixed before holdout inspection; visual references were assigned by the assistant afterward and were not blind to all outputs. These samples share scans, some scenes overlap, and the numeric cohort is enriched. Fresh positive Kana coverage, an independent human transcript set, and enough true POIs to bound rare suppression errors are still missing. No Taiwan-wide accuracy claim is supported.</p><p>The next useful experiment is a stronger character/line detector with explicit small-Kana and margin handling, evaluated on a newly labeled orientation-balanced set. For numbers, test upright preference as ranking rather than deletion, retaining alternatives. Improve those inputs before combining more evidence sources or changing background policy.</p><p><a href="evaluation.json">Metrics and per-case scores</a> · <a href="visual-references.json">References and limitations</a> · <a href="parameters.json">Locked parameters</a> · <a href="contract.json">Experiment contract</a> · <a href="sampling-addendum.json">Additional sampling and rounding notes</a> · <a href="evidence-ranking.json">Raw ranking replay</a> · <a href="rings.json">Raw ring findings</a></p><p>Reproduce in the project Python runtime: <code>tools/run_detection_proposals.py</code> (geometry/readings/rings), <code>tools/evaluate_proposal_evidence.py</code>, <code>tools/proposal_review_sheets.py</code>, then <code>tools/report_detection_proposals.py</code>. Frozen scene-run files refuse overwrite; use a new evidence directory for a new run. Source/model/input hashes and runtime details accompany outputs.</p></body></html>'
    doc=doc.replace('Each expanded patch is re-detected at four rotations.', 'Each expanded patch is re-detected at four outer rotations. “Upright-only” means no outer rotation; the existing detector still rectifies text and uses its built-in angle classifier. The rotations are correlated views, not independent readers.')
    (OUT/'report.html').write_text(doc,'utf-8')
    print(json.dumps(dict(geometry=geometry,names=name_scores,numbers_fresh={k:{x:y for x,y in v.items() if x!='samples'} for k,v in fresh_numbers.items()},numbers_development={k:{x:y for x,y in v.items() if x!='samples'} for k,v in oldnumeric.items()},kana={k:{x:y for x,y in v.items() if x!='controls'} for k,v in kana.items()},shifts=shifts),ensure_ascii=False,indent=2))
if __name__=='__main__':main()
