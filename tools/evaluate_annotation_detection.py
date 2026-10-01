"""Offline evaluation of frozen annotations; production never imports this tool.

Run with the project runtime from the repository root. The reduced input export
contains automatic features and evaluation classifications, without user notes.
This script never opens the live database or changes labels.
"""
import hashlib
import importlib.util
import json
import statistics
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from mapwalker.display import priority as landed_priority
from mapwalker.region_model import iou

OUT = ROOT / 'evidence/annotation-detection'
spec = importlib.util.spec_from_file_location('mapwalker.annotation_baseline', OUT/'baseline-display.py')
baseline = importlib.util.module_from_spec(spec)
spec.loader.exec_module(baseline)
priority = baseline.priority


def candidate(row, cutoff):
    rank = priority(row)
    details = row['details']
    box = row['box']
    width, height = abs(box[2]-box[0]), abs(box[3]-box[1])
    if (row['kind'] == 'symbol' and 'junction_count' not in details
            and details.get('area', 0) > 0
            and details['area'] / max(1, width*width+height*height) < cutoff):
        return min(rank, .58)
    return rank


def main():
    labels = OUT / 'inputs.json'
    rows = json.loads(labels.read_text('utf-8'))
    result = dict(baseline='6842eee', labels_sha256=hashlib.sha256(labels.read_bytes()).hexdigest(),
                  baseline_display_sha256=hashlib.sha256((OUT/'baseline-display.py').read_bytes()).hexdigest(),
                  split='source + 4x4 tile block SHA256 modulo 3; zero held out',
                  counts={}, samples=[], regressions=[], timing={})
    for r in rows:
        r['baseline'] = priority(r)
        r['candidate'] = candidate(r, .12)
        assert landed_priority(r) == r['candidate'], 'Landed policy differs from frozen candidate'
        result['samples'].append({k: r[k] for k in ('id', 'source', 'x', 'y', 'split', 'algorithm', 'baseline', 'candidate')} |
                                 dict(classification=r['annotation']['classification'], box=r['box'],
                                      area=r['details'].get('area')))
    for split in ('development', 'holdout'):
        result['counts'][split] = {}
        for classification in ('poi', 'noise', 'other'):
            selected = [r for r in rows if r['split'] == split and r['annotation']['classification'] == classification]
            result['counts'][split][classification] = dict(total=len(selected),
                baseline_top=sum(round(r['baseline'], 6) >= .74 for r in selected),
                candidate_top=sum(round(r['candidate'], 6) >= .74 for r in selected),
                reduced_eligibility_preserved=all((r['baseline'] >= .50) == (r['candidate'] >= .50) for r in selected))
    old = ROOT / 'evidence/symbol-first'
    runs = {r['scene']: r for r in map(json.loads, (old/'baseline-symbols.jsonl').read_text('utf-8').splitlines())}
    refs = json.loads((old/'references.json').read_text('utf-8'))['marks']
    for ref in refs:
        proposals = next(p for p in runs[ref['scene']]['passes'] if p['angle'] == 0)['proposals']
        hits = [p for p in proposals if iou(ref['box'], p['box']) >= .25]
        result['regressions'].append(dict(**ref,
            baseline_top=any(round(priority(p), 6) >= .74 for p in hits),
            rejected_candidate_top=any(round(candidate(p, .15), 6) >= .74 for p in hits),
            candidate_top=any(round(candidate(p, .12), 6) >= .74 for p in hits)))
    # Warm and time rank evaluation only, with JSON-decoded stored inputs.
    for name, fn in [('baseline', priority), ('candidate', lambda r: candidate(r, .12))]:
        for r in rows: fn(r)
        times = []
        for _ in range(40):
            for r in rows:
                start = time.perf_counter_ns(); fn(r)
                times.append((time.perf_counter_ns()-start)/1000)
        result['timing'][name] = dict(unit='microseconds per finding', mean=statistics.mean(times),
            median=statistics.median(times), p95=sorted(times)[int(.95*len(times))], maximum=max(times),
            excludes='database, decoding, I/O, GPU inference; candidate includes baseline call overhead')
    (OUT/'evaluation.json').write_text(json.dumps(result, ensure_ascii=False, indent=2), 'utf-8')
    print(json.dumps(result['counts'], indent=2))
    print('Known symbol Top coverage:', [(k, sum(r[k] for r in result['regressions'])) for k in
          ('baseline_top', 'rejected_candidate_top', 'candidate_top')])
    print(json.dumps(result['timing'], indent=2))


if __name__ == '__main__':
    main()
