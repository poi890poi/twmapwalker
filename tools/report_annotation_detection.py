"""Render the frozen annotation evaluation as a private, static evidence page."""
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT/'evidence/annotation-detection'


def main():
    result = json.loads((OUT/'evaluation.json').read_text('utf-8'))
    impact = json.loads((OUT/'impact.json').read_text('utf-8'))
    rows = ''
    for split, classes in result['counts'].items():
        for label, counts in classes.items():
            rows += (f'<tr><td>{split.title()}</td><td>{label.upper() if label == "poi" else label.title()}</td>'
                     f'<td>{counts["total"]}</td><td>{counts["baseline_top"]}</td><td>{counts["candidate_top"]}</td></tr>')
    page = '''<!doctype html><html lang="en"><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>Mapwalker · Learning from the annotations</title>
<style>body{font:17px/1.55 system-ui,sans-serif;background:#f4f2e9;color:#173e35;max-width:1080px;margin:auto;padding:24px}
h1{font-size:clamp(28px,5vw,46px);line-height:1.12}h2{line-height:1.2}section{background:white;padding:24px;margin:22px 0;border-radius:12px}
a{color:#006a79}table{border-collapse:collapse;width:100%}th,td{text-align:left;padding:10px;border-bottom:1px solid #ddd}
img{width:100%;height:auto}.scroll{overflow:auto}.note{border-left:4px solid #ad7525;padding:12px 18px;background:#fff9eb}
code{overflow-wrap:anywhere}small{color:#53655f}</style>
<a href="/">← Mapwalker</a><h1>Fewer contour fragments in Top quality</h1>
<p>2 October 2026 · Evaluated against your 68 saved annotations · Display policy 4</p>
<section><h2>What changed</h2><p>Thin, extended components from the symbol detector now receive lower display priority.
The old rule rewarded a unique shape and reasonable fill even when that shape was a broken contour line.
The new rule also checks how much ink the component contains relative to its overall span.</p>
<p><b>Top-eligible labeled noise: 41 → 30. Annotated POIs retained: 9 → 9.</b>
All findings, annotation history, detector IDs and raw detection results are preserved.
The affected symbols remain eligible for Reduced and Adaptive views, subject to their existing density limits,
and accessible in All candidates. OCR and CRAFT region scores are unchanged.</p></section>
<section><h2>Tested away from the development blocks</h2><div class="scroll"><table>
<tr><th>Split</th><th>Annotation</th><th>Labeled findings</th><th>Before: Top eligible</th><th>After: Top eligible</th></tr>''' + rows + '''</table></div>
<p>The held-out noise count fell from 27 to 22, with all four held-out POIs retained.
These are eligibility counts before map density selection and before hiding saved noise.
They are not the number of visible markers or an estimate of overall precision.</p>
<p class="note">The sample contains only nine confirmed POIs, all from text or region detectors.
There are no user-confirmed legacy symbol positives in it. Four previously eligible known symbols/characters
in an older independent reference set also remain eligible, but rare sparse symbols could still be demoted.
The split uses 4×4-tile blocks; neighboring blocks can share visual context. It is not a fresh session or
Taiwan-wide test. Missing features cannot be measured from annotations of existing detections.</p></section>
<section><h2>Actual affected map crops</h2><p>Thirty affected findings sampled by a fixed hash of their IDs,
across both map series. Red boxes show the original symbol components; the surrounding map is unchanged.
Visual inspection found the sample dominated by contour fragments. This qualitative check is not additional user ground truth.</p>
<img src="impact-sample.jpg" alt="Thirty examples of demoted symbol components on historical map crops">
<p>Across the frozen database, ''' + f'{impact["demoted"]:,} of {impact["top_eligible"]:,}' + ''' Top-eligible legacy symbols receive the cap.
That count describes scope, not correctly removed noise. No proposal is deleted.</p>
<small>Historical map imagery: 中央研究院 人社中心 GIS 專題中心. Cached source hashes verified for rendered crops.</small></section>
<section><h2>What I rejected and left unresolved</h2><p>A stronger cutoff (.15) also demoted the known 後 character,
so it was rejected. The conservative cutoff (.12) was frozen before evaluating the held-out labels.</p>
<p>Your Other annotations often identify contour elevations, while some numbers are useful POIs.
Suppressing numbers indiscriminately would discard wanted features. This change therefore leaves numeric text,
Other classifications and small compact noise unchanged. It improves prioritization, not raw detection recall or name recognition.</p>
<p>Scoring needs only stored geometry and ink area. It does not consult your live annotations or need a trained model.
The offline labels evaluate the rule. Per-finding scoring was measured in microseconds, separately from database,
image decoding and detector inference; see the raw timing record. No detector speedup is claimed.</p></section>
<section><h2>Evidence and reproduction</h2><p><a href="contract.md">Decision contract</a> ·
<a href="evaluation.json">Per-finding results and timing</a> · <a href="inputs.json">Frozen reduced input export</a> ·
<a href="impact.json">Scope and sample IDs</a> · <a href="baseline-display.py">Frozen baseline policy</a></p>
<p>Run <code>python tools/evaluate_annotation_detection.py</code>, then
<code>python tools/report_annotation_detection.py</code> with the project runtime.
The evaluator verifies that the implemented policy matches the frozen candidate on every annotated finding.</p>
<p>Verification: 34 focused tests passed, covering display ranking, annotations, browsing and visibility,
including map/list/export consistency, lower-tier access, and saving Noise without promoting neighbors.</p></section></html>'''
    (OUT/'report.html').write_text(page, 'utf-8')


if __name__ == '__main__':
    main()
