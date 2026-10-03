"""Package assistant visual review of the frozen development contact sheets."""
import hashlib
import html
import json
from collections import Counter
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
OUT=ROOT/'evidence/contour-samples'
# Recorded after viewing all twelve sheets. These are visual assessments,
# not miner predictions, user annotations, or independently verified semantics.
EXCEPTIONS={
    'uncertain':[6,30,46,47,52,53,59,60,82,84,99,112,114,137,143,147,162,178],
    'vegetation-like':[34,90,97,98,102,106,117,131,141,145,156,159,160,161,182,186],
    'text':[37,100,101,129,130,140,152,175],
    'numeric':[56,66,94,135,136,138,139,185,187,190],
    'other-repeated-symbol':[181,183],
}


def digest(path):return hashlib.sha256(path.read_bytes()).hexdigest()


def write(name,value):
    (OUT/name).write_text(json.dumps(value,ensure_ascii=False,indent=2)+'\n',encoding='utf8')


def main():
    if (OUT/'visual-labels.json').exists():raise RuntimeError('Preserve recorded review')
    rows=json.loads((OUT/'dataset.json').read_text(encoding='utf8'))
    dev=[r for r in rows if r['split']=='development'];reserved=[r for r in rows if r['split']=='reserved-evaluation']
    assert {r['index'] for r in dev}==set(range(1,193))
    exceptions={i:label for label,indices in EXCEPTIONS.items() for i in indices}
    assert len(exceptions)==sum(map(len,EXCEPTIONS.values()))
    labels=[];training=[]
    for r in dev:
        label=exceptions.get(r['index'],'contour-fragment')
        target='contour-negative' if label=='contour-fragment' else 'protected-glyph' if label in ('text','numeric') else 'exclude'
        labels.append(dict(id=r['id'],index=r['index'],label=label,training_role=target))
        if target!='exclude':training.append({**r,'label':label,'training_role':target})
    # Verify every native crop, spatial split, deduplication and source boundary.
    assert len({(r['x'],r['y']) for r in rows})==len(rows)
    assert not ({r['block'] for r in dev}&{r['block'] for r in reserved})
    for r in rows:
        assert digest(OUT/r['context'])==r['context_sha256']
        assert digest(OUT/r['mark'])==r['mark_sha256']
    for a in dev:
        for b in reserved:
            assert max(abs(a['x']-b['x']),abs(a['y']-b['y']))>=3
            assert not {(p['z'],p['x'],p['y']) for p in a['sources']} & {(p['z'],p['x'],p['y']) for p in b['sources']}
    # Keep old rare-symbol controls separate from newly collected training rows.
    old=ROOT/'evidence/noise-verifier/dataset.json'
    guards=[r for r in json.loads(old.read_text(encoding='utf8')) if r['split']=='regression-control']
    write('protection-controls.json',dict(dataset=old.relative_to(ROOT).as_posix(),sha256=digest(old),
        controls=[dict(id=r['id'],name=r['name'],crop=r['crop'],sha256=r['sha256']) for r in guards],
        role='Reused protection controls, including hot spring and school. Never training examples or fresh accuracy evidence.'))
    write('visual-labels.json',dict(provenance='Assistant visual inspection of development-00.jpg through development-11.jpg; region inside red box, using surrounding context.',
        rules='Contour-negative requires a visible contour continuation or repeated parallel contour geometry. Numerals and text remain protected even if they might be contour labels. Other and uncertain symbols are excluded, not relabelled as noise. Labels apply only to the boxed target, not every mark in its context.',
        labels=labels,reserved_labels='Not inspected or labelled.'))
    write('training.json',training)
    counts=dict(Counter(r['label'] for r in labels))
    summary=dict(development=len(dev),reserved=len(reserved),label_counts=counts,
        contour_negatives=sum(r['training_role']=='contour-negative' for r in training),
        protected_glyphs=sum(r['training_role']=='protected-glyph' for r in training),
        top_ranked_contour_negatives=sum(r['training_role']=='contour-negative' and r['priority']>=.74 for r in training),
        geographic_blocks=len({r['block'] for r in rows}),development_blocks=len({r['block'] for r in dev}),reserved_blocks=len({r['block'] for r in reserved}),
        validation=['426 native crop hashes verified','No geographic tile or 4x4 block shared across splits, including different editions',
                    'No source tile used by both a development and reserved crop','At least three native-tile index separation across splits',
                    'Reserved pixels not shown on contact sheets or used to select visual labels'],
        limitations=['Assistant labels need independent verification before a safety claim.',
                     '192 region-centred contexts are not 192 entirely negative images; context can contain real text and symbols.',
                     '21 reserved samples were available under the strict prior-study buffer; the target of 64 was not met.',
                     'This is a training-data deliverable. No classifier has been trained, validated or enabled.'])
    write('summary.json',summary)
    cards=''.join(f'<a href="development-{i:02}.jpg"><img loading="lazy" src="development-{i:02}.jpg" alt="Development sample contact sheet {i+1}"></a>' for i in range(12))
    table=''.join(f'<tr><td>{html.escape(k)}</td><td>{v}</td></tr>' for k,v in counts.items())
    (OUT/'report.html').write_text(f'''<!doctype html><html lang="en"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>Contour hard-negative samples</title>
<style>body{{max-width:1100px;margin:24px auto;padding:0 18px;background:#fafaf5;color:#203b32;font:17px/1.6 system-ui}}img{{max-width:100%;height:auto}}table{{border-collapse:collapse}}td{{padding:6px 18px;border-bottom:1px solid #ccc}}a{{color:#24684d}}.notice{{padding:16px;background:#edf0df}}</style>
<a href="/">Back to map</a><h1>Contour fragments are abundant</h1><p>3 October 2026 · Real detector proposals at native z16 scale.</p>
<p class="notice">Collected and visually reviewed 192 development samples: <strong>{summary['contour_negatives']} contour negatives</strong>, including <strong>{summary['top_ranked_contour_negatives']} admitted by the current Top threshold</strong>. Kept {summary['protected_glyphs']} text/number examples as protected glyphs. Other symbols and uncertain marks are excluded from binary training.</p>
<table>{table}</table><p>Examples include broken strokes, sharp bends, hairpins and merged contour lines, across both 1916 and 1924 editions. Their original appearance and size are preserved in native PNGs; each target also has 192×192 pixels of surrounding map context. Contact sheets enlarge every context by the same factor, with no aspect-ratio distortion.</p>
<p>The miner found 12,328 eligible proposals after its size, geographic and prior-study filters. This is a candidate pool, not 12,328 labelled contour negatives. We froze another {len(reserved)} samples from {summary['reserved_blocks']} separate geographic blocks for later evaluation. They are not inspected or labelled here. The 64-sample reserve target could not be met under the strict exclusion rules.</p>
<p><strong>Use the boxed target.</strong> Real text, numbers or vegetation can occur elsewhere in the context. Treating the entire context image as noise would teach the wrong task. No marks were deleted, hidden or reclassified in the application.</p>
<p>Labels below are assistant visual judgements. This dataset supplies training material; it does not establish detector precision or justify automatic hiding. The existing rare-symbol controls remain outside training. A later model must also pass an expanded independent positive set.</p>
<p><a href="training.json">Training manifest</a> · <a href="visual-labels.json">Labels and excluded cases</a> · <a href="dataset.json">Full frozen sample manifest</a> · <a href="summary.json">Verification</a></p><h2>Development contact sheets</h2><p>Click a sheet for its full size. Reserved evaluation pixels are intentionally not displayed.</p>{cards}</html>''',encoding='utf8')
    write('artifact-manifest.json',{p.relative_to(ROOT).as_posix():digest(p) for p in sorted(OUT.rglob('*')) if p.is_file() and p.name!='artifact-manifest.json'} |
          {p.relative_to(ROOT).as_posix():digest(p) for p in [ROOT/'tools/mine_contour_samples.py',Path(__file__)]})
    print(json.dumps(summary,indent=2))


if __name__=='__main__':main()
