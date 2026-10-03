"""Freeze completed backfill telemetry and verify original records are intact."""
import gzip
import hashlib
import json
import sqlite3
from pathlib import Path

import numpy as np
from mapwalker.paths import ROOT, default_data

OUT=ROOT/'evidence/vegetation-backfill'


def main():
    db=sqlite3.connect('file:'+(default_data()/'mapwalker.sqlite3').as_posix()+'?mode=ro',uri=True)
    db.row_factory=sqlite3.Row
    run=dict(db.execute('SELECT * FROM vegetation_runs ORDER BY id DESC LIMIT 1').fetchone())
    assert run['state']=='complete', 'Wait for the scan to finish'
    after={}
    for name in ('pois','annotations','reviews','readings','poi_visibility'):
        rows=[tuple(r) for r in db.execute('SELECT * FROM '+name+' ORDER BY id')]
        after[name]=dict(rows=len(rows),sha256=hashlib.sha256(json.dumps(rows,ensure_ascii=False,separators=(',',':')).encode()).hexdigest())
    (OUT/'after.json').write_text(json.dumps(after,indent=2),'utf-8')
    before=json.loads((OUT/'before.json').read_text('utf-8'))
    preserved={name:after[name]==before[name] for name in before}
    original_rows=[tuple(r) for r in db.execute('SELECT * FROM pois WHERE id<=? ORDER BY id',(run['ceiling'],))]
    original_pois=dict(rows=len(original_rows),sha256=hashlib.sha256(json.dumps(original_rows,ensure_ascii=False,separators=(',',':')).encode()).hexdigest())
    preserved['pois']=original_pois==before['pois']
    checks=[dict(r) for r in db.execute('SELECT * FROM vegetation_checks WHERE profile=? ORDER BY poi_id',(run['profile'],))]
    payload='\n'.join(json.dumps(r,separators=(',',':')) for r in checks).encode()
    (OUT/'checks.jsonl.gz').write_bytes(gzip.compress(payload,mtime=0))
    counts={r['status']:r['n'] for r in db.execute('SELECT status,count(*) n FROM vegetation_checks WHERE profile=? GROUP BY status',(run['profile'],))}
    durations=[r['elapsed_ms'] for r in checks]
    run.pop('owner');run['metadata']=json.loads(run['metadata'])
    summary=dict(run=run,counts=counts,original_records_unchanged=preserved,
                 original_pois=original_pois,new_detection_rows_after_snapshot=after['pois']['rows']-len(original_rows),
                 elapsed_seconds=run['updated']-run['created'],
                 per_proposal_ms=dict(mean=float(np.mean(durations)),median=float(np.median(durations)),p95=float(np.percentile(durations,95)),maximum=max(durations)),
                 errors=[dict(id=r['poi_id'],detail=json.loads(r['evidence'])) for r in checks if r['status']=='error'],
                 checks_uncompressed_sha256=hashlib.sha256(payload).hexdigest(),
                 automatic_classifications=0, interpretation='Proposal counts only. Suggestions have not been independently labeled; no precision or recall claim. Duplicates of physical marks can appear.',
                 verification=dict(python='22 focused tests passed across the initial suite and subsequent lease/annotation regression run',javascript='4 suites passed: vegetation_review, vegetation_evidence, annotation_save, suggestion_selection',live='Private HTTPS queue, empty initial selection, select/clear, pagination and exact-POI link verified. No production Save/Dismiss performed.',mobile='Phone viewport eventually applied after refresh:415px content width, no horizontal overflow, individual selection and clear verified. Initial override was delayed.'))
    (OUT/'summary.json').write_text(json.dumps(summary,ensure_ascii=False,indent=2),'utf-8')
    assert all(preserved.values()), 'Concurrent changes found; do not claim records were unchanged'
    (OUT/'report.html').write_text(f'''<!doctype html><html lang="en"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>Existing-candidate vegetation scan · Mapwalker</title><style>body{{font:18px/1.6 system-ui;color:#17322f;background:#f5f5ed;max-width:1000px;margin:32px auto;padding:20px}}h1{{line-height:1.2}}a{{color:#17624f}}img{{max-width:100%}}table{{border-collapse:collapse;background:white;width:100%}}td,th{{text-align:left;padding:12px;border-bottom:1px solid #ccd8cb}}</style><h1>Existing candidates are ready for review</h1><p><a href="/vegetation-review.html">Open the live vegetation review queue →</a></p><table><tr><th>Outcome</th><th>Proposal count</th></tr><tr><td>Scanned</td><td>{run['processed']:,}</td></tr><tr><td>Possible vegetation</td><td>{counts.get('candidate',0):,}</td></tr><tr><td>Numeric-context veto</td><td>{counts.get('numeric-context',0):,}</td></tr><tr><td>No matching pattern</td><td>{counts.get('no-match',0):,}</td></tr><tr><td>Unavailable evidence</td><td>{counts.get('error',0):,}</td></tr></table><p>Completed in {(run['updated']-run['created'])/60:.1f} minutes. All {len(original_rows):,} original detection rows and every existing annotation, review, reading and visibility record have identical pre/post hashes. Normal detection added {summary["new_detection_rows_after_snapshot"]} new rows after the frozen scan boundary; these belong to a later scan. No production finding was classified or dismissed.</p><p>The landed native-size method is unchanged. This run backfills suggestions only. These are candidate IDs, including duplicate detections; they are neither unique vegetation symbols nor verified noise labels. Unavailable and uncertain findings remain visible.</p><p>Choose individual rows or a page, then Save selected as Other to hide those findings using the existing recoverable annotation flow. Dismiss selected suggestions to leave their findings unchanged. All selections begin empty. Saved manual work and edits made since scanning are protected by transaction-time checks.</p><img src="queue-preview.png" alt="Live vegetation review queue with original-map previews and zero selected proposals"><p>22 focused Python tests and four JavaScript suites passed. Live desktop queue, pagination and exact-POI links were checked. The phone layout was also verified at415px content width, with no horizontal overflow and working select/clear controls.</p><p><a href="contract.md">Contract</a> · <a href="summary.json">Counts, timings, method fingerprint and verification</a> · <a href="before.json">Before</a> · <a href="after.json">After</a> · <a href="checks.jsonl.gz">Frozen per-proposal telemetry</a> · <a href="artifact-manifest.json">Artifact hashes</a></p><p>Run or resume with <code>python -m tools.backfill_vegetation</code> from the repository in the configured runtime. Completed checks with unchanged inputs are reused; errors are retried. Older versions remain recorded separately.</p></html>''','utf-8')
    db.close()
    print(json.dumps(dict(counts=counts,original_records_unchanged=preserved,elapsed_seconds=summary['elapsed_seconds']),indent=2))


if __name__=='__main__':main()
