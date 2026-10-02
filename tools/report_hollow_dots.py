"""Build a private reference page for the offline hollow-dot investigation."""
import hashlib
import html
import json
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
OUT=ROOT/'evidence/hollow-dot'
GSI='https://service.gsi.go.jp/map-photos/contents/screen/mapphoto/images/legend/'
SOURCES=[
    dict(id='gsi-1900',title='1900 / Meiji 33 topographic legend',url=GSI+'m33.jpg',file='meiji33-legend.jpg',role='Earlier comparison; not assigned automatically to a Taiwan layer.'),
    dict(id='gsi-1909',title='1909 / Meiji 42 topographic legend',url=GSI+'m42.jpg',file='meiji42-legend.jpg',role='Period comparison, not proof of the 1916 layer specification.'),
    dict(id='gsi-1917',title='1917 / Taisho 6 topographic legend',url=GSI+'t6.jpg',file='taisho6-legend.jpg',role='Period reference for the 1924 army map; exact sheet edition still needs checking.'),
    dict(id='sinica-symbols',title='Academia Sinica: Taiwan topographic map symbol catalogue',url='https://thcts.sinica.edu.tw/themes/rd15.php',role='Taiwan-specific named symbols; page lists 5,270 digitized points. Download requires login.'),
    dict(id='sinica-baotu',title='Academia Sinica: Taiwan Baotu symbol catalogue',url='https://thcts.sinica.edu.tw/themes/rd01-1.php',role='Earlier Taiwan symbol family.'),
    dict(id='sinica-history',title='Academia Sinica: Taiwan surveying chronology',url='https://gis.rchss.sinica.edu.tw/mapclub_20250806/',role='States that the 1909-1916 mountain series uses the Baotu symbol system.'),
    dict(id='sinica-1916',title='Academia Sinica: 1907-1916 mountain map names',url='https://thcts.sinica.edu.tw/themes/rd13-1.php',role='Historical names and an Excel resource are listed; not imported or validated here.'),
    dict(id='sinica-landuse',title='Academia Sinica: historical land-use symbol detection',url='https://gis.rchss.sinica.edu.tw/wp-content/uploads/2025/12/20251127_map_ai_04.pdf',role='Page 4 compares Taiwan legends; later slides describe YOLOv8 experiments. No weights acquired.'),
]
CATALOG=[
    ('broadleaf-forest','闊葉樹林','Hollow crowns with short stems, scattered in an area; accompanying dots can occur.','Area texture candidate. Require repeated spatial context; a single tree is not enough.','taisho6-vegetation-detail.png'),
    ('individual-tree','獨立樹','The point-symbol legend explicitly includes individual broadleaf and conifer trees.','Protect as a potential landmark; shape overlaps the forest texture.','taisho6-individual-trees.png'),
    ('conifer-bamboo','針葉樹林 / 竹林','Repeated pointed crowns or branched strokes.','Potential area texture; do not confuse an isolated triangle with a survey marker.','meiji42-vegetation.png'),
    ('agriculture','茶畑 / 果園 / 桑畑 / 水田','Dot clusters, small crowns and repeated strokes distinguish different land uses.','Recognize the pattern and its extent, not individual punctuation-like components.','taisho6-landuse.png'),
    ('government-office','町村役場 / 區役所','Some public-office symbols are hollow circles.','Protect: roundness does not imply vegetation or noise.','taisho6-public-offices.png'),
    ('survey-elevation','三角點 / 水準點 / 獨立標高點','The legend pairs different point symbols with elevation numbers.','Protect the marker-number association. Verify sheet units before comparison with DEM.','taisho6-survey-points.png'),
    ('spring','礦泉 / 湧泉','The legend distinguishes mineral springs from flowing springs.','Protect complete symbols; do not reduce them to loops or trailing strokes.','taisho6-springs-detail.png'),
    ('institutions','學校 / 警察署 / 病院 / 郵便局','Compact symbols name public institutions. Taiwan-specific tables provide additional references.','Protect, including damaged symbols whose strokes resemble crosses or vegetation.','taisho6-landmarks.png'),
    ('religion','神祠 / 佛宇 / 祠廟 / 西教堂','Taiwan-specific tables distinguish multiple religious sites.','Separate target classes for POI recognition; do not merge into generic text noise.','taisho6-religion.png'),
    ('closed-contour','Closed contours','Loops of varying size nested among other contours; these occur in the user Other examples.','Terrain evidence. Do not classify every loop as a tree or automatically remove summit context.','17009.png'),
]


def main():
    for source in SOURCES:
        if 'file' in source:
            source['sha256']=hashlib.sha256((OUT/source['file']).read_bytes()).hexdigest()
    catalog=dict(role='Research reference only; no production rules or annotation changes.',
        sources=SOURCES,symbols=[dict(id=i,name=n,appearance=a,handling=h,image=im,
             interpretation='Assistant synthesis from cited legends; exact Taiwan sheet applicability must be checked.')
             for i,n,a,h,im in CATALOG])
    (OUT/'legend-catalog.json').write_text(json.dumps(catalog,ensure_ascii=False,indent=2),'utf-8')
    contract=dict(type='Offline algorithm experiment and historical-symbol research',
        intended_outcome='High precision when flagging non-POI vegetation, prioritizing preservation of real POIs.',
        old_and_new_behavior='Production unchanged. New offline probe and browsable legend catalogue only.',
        runtime_inputs=['cached image pixels','automatic detection box'],
        evaluation_only=['frozen user classifications','assistant morphology labels','prior user-identified reference boxes'],
        preserve=['all stored candidates','all Other labels','POI visibility and ranking','OSM links','annotations'],
        failure_modes=['zeros/characters mistaken for rings','individual trees or offices mistaken for forest','merged contours obscure stems/dots'],
        acceptance='No automatic suppression without independent evidence of sufficiently low POI rejection; no absolute guarantee from this sample.',
        decision='Reject ring-only suppression; retain compound probe as research. Only 1/17 vegetation-like findings flagged, zero of 23 user POI findings and 10 prior protected references. Not deployment evidence.')
    (OUT/'contract.json').write_text(json.dumps(contract,indent=2),'utf-8')
    source_links=''.join(f'<li><a href="{s["url"]}">{html.escape(s["title"])}</a> — {html.escape(s["role"])}</li>' for s in SOURCES)
    cards=''.join(f'<article><h3>{html.escape(name)}</h3><a href="{im}"><img loading="lazy" src="{im}" alt="{html.escape(name)} legend or map crop"></a><p>{html.escape(appearance)}</p><p class="handling">{html.escape(handling)}</p></article>' for _,name,appearance,handling,im in CATALOG)
    page='''<!doctype html><html lang="en"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>Mapwalker · Reading the hollow dots</title><style>
:root{color-scheme:light}*{box-sizing:border-box}body{margin:0;background:#f3f1e8;color:#173e35;font:17px/1.55 system-ui,sans-serif}
main{max-width:1140px;margin:auto;padding:24px}h1{font-size:clamp(32px,6vw,54px);line-height:1.08;margin:20px 0}h2{line-height:1.25}a{color:#006b78}
section{background:white;border-radius:14px;padding:24px;margin:24px 0}.intro{max-width:850px}.note{background:#fff4db;border-left:4px solid #a57221;padding:16px}
.grid{display:grid;grid-template-columns:repeat(auto-fit,minmax(265px,1fr));gap:20px}article{padding:16px;border:1px solid #d8dfd8;border-radius:10px;overflow:hidden}
article h3{margin:0 0 12px}article img{width:100%;height:250px;object-fit:contain;background:#faf8ef}img{max-width:100%;height:auto}
.handling{font-weight:600}.examples{display:flex;flex-wrap:wrap;gap:20px}.examples figure{margin:0;flex:1;min-width:210px}.examples img{width:200px;image-rendering:pixelated}figcaption{font-size:15px}
table{width:100%;border-collapse:collapse}th,td{text-align:left;padding:10px;border-bottom:1px solid #ddd}.scroll{overflow:auto}small{color:#52685e}li{margin:10px 0}
</style><main><a href="/">← Mapwalker</a><h1>Reading the hollow dots</h1><p>2 October 2026 · Historical legends and a precision-first detector experiment</p>
<section class="intro"><h2>Many are forest symbols. Some lookalikes are real POIs.</h2>
<p>The repeated small hollow crowns, stems and dots in your 1924 examples closely match <b>闊葉樹林</b>, broadleaf forest. This is a supported interpretation of the examples, not a verified identification of every circle.</p>
<div class="examples"><figure><img src="17042.png" alt="User Other example 17042, small hollow crown and stem"><figcaption>Your example #17042</figcaption></figure>
<figure><img src="legend-vegetation.png" style="width:auto;height:200px;object-fit:contain" alt="1917 legend with broadleaf forest symbols"><figcaption><a href="legend-vegetation.png">1917 vegetation legend: enlarge</a></figcaption></figure>
<figure><img src="17009.png" alt="User example of a larger closed contour"><figcaption>#17009: a different kind of loop</figcaption></figure></div>
<p class="note"><b>Do not suppress circles by shape alone.</b> The same legend explicitly marks individual trees as landmarks, and uses hollow circles for some public offices. Repeated area texture and isolated point symbols need different treatment.</p></section>
<section><h2>Which legend belongs with which map?</h2><p>The GSI scans cover 1900, 1909 and 1917 specifications. Their publication dates are useful clues, but not proof that a Taiwan sheet used that exact edition.</p>
<p>Academia Sinica's surveying chronology states that the 1909–1916 mountain maps used the <b>Taiwan Baotu symbol system</b>. Therefore the 1916 layer should not simply inherit the 1909 Japanese legend. The Taiwan Baotu table and the Taiwan-specific topographic table are essential cross-checks.</p>
<p><a href="meiji33-legend.jpg">1900 full legend</a> · <a href="meiji42-legend.jpg">1909 full legend</a> · <a href="taisho6-legend.jpg">1917 full legend</a> · <a href="sinica-landuse-legend.png">Academia Sinica's Taiwan land-use comparison</a></p></section>
<section><h2>Other symbols worth teaching the detector</h2><p>These are reference families, not active filters. Click any image to inspect the source crop. Original historical text often runs right to left.</p><div class="grid">'''+cards+'''</div>
<p>Further target classes in the Taiwan tables include monuments, wells, mines, watermills and weather stations. These can support recognition of meaningful POIs, even where OCR produces no name.</p></section>
<section><h2>What the pixel experiment actually found</h2><div class="scroll"><table><tr><th>Probe</th><th>Vegetation-like / 17</th><th>User POIs flagged / 23</th><th>Protected references flagged / 10</th></tr>
<tr><td>Small enclosed ring</td><td>14</td><td>12</td><td>5</td></tr><tr><td>Ring + stem + nearby dot, stable thresholds</td><td>0</td><td>0</td><td>0</td></tr>
<tr><td>Same rule, slightly larger allowed dot</td><td>1</td><td>0</td><td>0</td></tr></table></div>
<p>The broad rule also hit 9 of 12 numeric findings. It is rejected for filtering. The compound rule remained too brittle: dots merged into contours, and some crowns lost their holes as the image threshold changed. Increasing only the dot-area ceiling from 30 to 45 pixels recovered #17042, but none of six vegetation-like findings in the southern check.</p>
<p class="note">These are counts of findings, not independent objects or an estimate of global precision. Some findings overlap the same mark. The 17 vegetation-like labels are assistant visual interpretations of your Other annotations. The southern examples were viewed before the experiment, so they are not a blind holdout. Zero POI errors in this small sample does not establish safe automatic suppression.</p>
<p><b>Decision: no production filtering change.</b> A useful next candidate is a small classifier or object detector trained on complete symbols and surrounding context, with explicit classes for vegetation, individual trees, offices, survey marks, numbers and unknowns. Legend templates can supply reference shapes; real map crops and hard negatives must establish precision on unseen sheets.</p>
<p>Academia Sinica has tested YOLOv8 for historical land-use symbols. That supports investigating a specialist model, but its reported results are not validation for these layers or our POI-preservation requirement.</p>
<details><summary>Inspect the actual probe examples</summary><img loading="lazy" src="evaluation-dot45-sheet.jpg" alt="Map crops for ring detections and protected reference symbols"></details></section>
<section><h2>Useful existing historical data</h2><p>The Taiwan topographic symbol table already lists <b>5,270 digitized points</b>. A separate 1907–1916 map-name page lists an Excel resource. These could provide historical recognition evidence alongside OSM, subject to access, coverage and sheet-alignment checks. Neither dataset was imported or used to score this experiment.</p></section>
<section><h2>Sources and reproduction</h2><ul>'''+source_links+'''</ul><p>Legend scans: Geospatial Information Authority of Japan. Map crops: Academia Sinica GIS Center, existing immutable local tile cache. Interpretations and algorithm evaluation: this investigation.</p>
<p><a href="legend-catalog.json">Machine-readable source and symbol catalogue</a> · <a href="contract.json">Scope and decision</a> · <a href="evaluation.json">Initial compound probe</a> · <a href="evaluation-dot45.json">Single-variable follow-up</a> · <a href="other-sheet.jpg">All 34 Other examples</a></p>
<p>Reproduce with <code>python tools/probe_hollow_dots.py</code>, then <code>python tools/probe_hollow_dots.py --satellite-max 45 --output-stem evaluation-dot45</code>, followed by <code>python tools/report_hollow_dots.py</code>. Cached source hashes are checked. The probe receives only pixels and automatic boxes; annotations are evaluation inputs only.</p>
<small>All candidates, annotations, visibility and ranking remain unchanged.</small></section></main></html>'''
    (OUT/'report.html').write_text(page,'utf-8')
    print('Wrote',OUT/'report.html')


if __name__=='__main__':main()
