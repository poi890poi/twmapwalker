"""Replay display simplifications against a frozen DB audit, without DB writes."""
import gzip
import hashlib
import html
import json
import sys
from collections import Counter
from pathlib import Path

from mapwalker.display import priority

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / 'evidence/noise-usability'


def main():
    snapshot = ROOT / 'data/noise-usability/baseline.json'
    replay = '--replay' in sys.argv
    if replay:
        frozen = json.loads(gzip.decompress((OUT/'inputs.json.gz').read_bytes()))
        automatic = frozen['automatic']
        references = {int(k):v for k,v in frozen['references'].items()}
        snapshot_hash = json.loads((OUT/'summary.json').read_text(encoding='utf8'))['snapshot_sha256']
    else:
        rows = json.loads(snapshot.read_text(encoding='utf8'))
        references = {r['id']:r['annotation']['classification'] for r in rows if r['annotation']}
        automatic = [dict(id=r['id'], kind=r['kind'], algorithm=r['algorithm'], text=r['text'],
                          box=r['box'], rank=round(priority(r), 6)) for r in rows]
        snapshot_hash = hashlib.sha256(snapshot.read_bytes()).hexdigest()
    # Frozen automatic fields for the historical controls, not their semantics.
    controls = [dict(id=7,rank=.74,box=[35,25,55,44],text=''),
                dict(id=8,rank=.25,box=[111,36,117,43],text=''),
                dict(id=9,rank=.74,box=[176,38,197,57],text='')]
    methods = {
        'Current top threshold': lambda r:r['rank'] >= .74,
        'Raise threshold to 0.80': lambda r:r['rank'] >= .80,
        'Raise threshold to 0.85': lambda r:r['rank'] >= .85,
        'Require extent of 24 pixels': lambda r:r['rank'] >= .74 and max(r['box'][2]-r['box'][0],r['box'][3]-r['box'][1]) >= 24,
        'Require recognized text': lambda r:r['rank'] >= .74 and bool(r['text'].strip()),
    }
    results = []
    for name, accepts in methods.items():
        predicted = {r['id'] for r in automatic if accepts(r)}
        labelled = Counter(label for pid,label in references.items() if pid in predicted)
        missed = sorted(pid for pid,label in references.items() if label == 'poi' and pid not in predicted)
        results.append(dict(method=name,admitted=len(predicted),poi=labelled['poi'],
                            noise=labelled['noise'],other=labelled['other'],missed_poi_ids=missed,
                            controls_retained=[r['id'] for r in controls if accepts(r)],
                            decision='baseline' if name=='Current top threshold' else 'reject: loses known meaningful findings'))
    assert results[0]['noise'] and results[0]['other'] # Metric detects the known failure.
    assert all(r['missed_poi_ids'] or 9 not in r['controls_retained'] for r in results[1:])
    assert 9 in results[0]['controls_retained']
    summary = dict(snapshot_sha256=snapshot_hash,
                   rows=len(automatic),reference_counts=dict(Counter(references.values())),
                   top_sources=dict(Counter(r['algorithm'] for r in automatic if r['rank']>=.74)),
                   results=results,
                   scope='Threshold eligibility before density selection and saved-annotation visibility. Previously marked Noise/Other remain hidden in the actual viewer.',
                   limitations=['User-selected existing annotation set; not a random sample, fresh holdout, prevalence or precision estimate.',
                                'POI counts are finding records, including multiple fragments/duplicates, not distinct landmarks.',
                                'Other includes real non-POI features and ambiguous marks; it is not a blanket noise training label.',
                                'Known controls are reused diagnostic references. Control 8 already fails the current top threshold.',
                                'Each simplification fails known positive controls, so no fresh holdout or production change is justified.'])
    if replay:
        assert summary == json.loads((OUT/'summary.json').read_text(encoding='utf8'))
        print('All five display-rule results reproduce from frozen automatic inputs and separate evaluation labels.')
        return
    OUT.mkdir(exist_ok=False)
    telemetry = dict(automatic=automatic,references=references,controls=controls)
    (OUT/'inputs.json.gz').write_bytes(gzip.compress(json.dumps(telemetry,ensure_ascii=False,separators=(',',':')).encode(),mtime=0))
    (OUT/'summary.json').write_text(json.dumps(summary,ensure_ascii=False,indent=2)+'\n',encoding='utf8')
    table = ''.join('<tr>'+''.join(f'<td>{html.escape(str(v))}</td>' for v in
                    [r['method'],r['admitted'],r['poi'],r['noise'],r['other'],9 in r['controls_retained']])+'</tr>' for r in results)
    (OUT/'report.html').write_text('''<!doctype html><html lang="en"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>Why the default map is still noisy</title><style>body{margin:24px auto;padding:0 18px;max-width:980px;font:17px/1.6 system-ui;color:#17362e;background:#fafaf5}table{border-collapse:collapse;width:100%;font-size:14px}td,th{padding:10px;border-bottom:1px solid #ccd5cd;text-align:left}.table{overflow-x:auto}a{color:#22644d}</style>
<a href="/">Back to map</a><h1>Why the default map is still noisy</h1><p>3 October 2026 · Read-only diagnostic replay. No detector, ranking, annotations or visibility changed.</p>
<p>The current threshold admits 25,866 of 110,988 active text/symbol candidates before density thinning. Of these, 20,660 come from generic connected shapes, 4,890 from unread region proposals, and only 316 from the two OCR pipelines. This is shape salience, not evidence that a mark is a meaningful landmark.</p>
<p>On the existing user-labelled sample, automatic features alone admit 100 of 113 Noise/Other findings, along with all 39 POI findings. Their saved Noise/Other annotations already hide them in the actual viewer; this replay measures the ranking rule without that manual correction.</p>
<div class="table"><table><tr><th>Rule</th><th>All admitted</th><th>POI / 39</th><th>Noise / 59</th><th>Other / 54</th><th>Hot spring 9 retained</th></tr>'''+table+'''</table></div>
<p><strong>Decision: reject all four simplifications.</strong> Raising the threshold or requiring successful OCR loses known POI records. A small-size cutoff preserves this annotation set but loses the separate hot-spring and height-symbol controls. It would look cleaner by removing meaningful findings too.</p>
<p>The vegetation backfill proposed only 213 of 110,372 checked fragments (0.19%). Even perfect acceptance of that set could not materially solve general map clutter. Its coverage count is not vegetation recall or precision.</p>
<h2>What this evidence changes</h2><p>Generic shape scores and rotation agreement cannot justify the “Top quality” implication. The next detector experiment must distinguish contour fragments, vegetation, text/Kana, numerals and landmark symbols using the original mark and surrounding map, with an explicit uncertain outcome. Its acceptance test is reduced non-POI clutter on complete held-out map areas while retaining independent rare-symbol and unread-text controls. Additional review widgets do not address this bottleneck.</p>
<p>Do not use all Other marks as training negatives, require an OSM name match, or classify every number as a contour label. These rules can erase real symbols, historical names and peak heights.</p>
<h2>Limits</h2><p>This is a reused, user-selected annotation set, with duplicate fragments and uneven classes. These counts are not precision, recall or a map-wide false-positive rate. None of the failing methods was promoted to a fresh validation trial or production. This audit diagnoses the failure; it does not claim noise removal has been solved.</p>
<p><a href="summary.json">Full counts and missed POI IDs</a> · <a href="inputs.json.gz">Frozen automatic inputs and separate evaluation labels</a></p></html>''',encoding='utf8')
    print(json.dumps(summary,ensure_ascii=False,indent=2))


if __name__ == '__main__':
    main()
