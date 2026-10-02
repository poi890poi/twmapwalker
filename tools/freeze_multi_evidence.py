"""Freeze automatic detections, separate evaluation labels, and source provenance."""
import csv
import hashlib
import json
import sqlite3
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT/'data/multi-evidence'
OUT = ROOT/'evidence/multi-evidence'


def write(path, value):
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2)+'\n', 'utf-8')


def main():
    OUT.mkdir(exist_ok=True)
    if (OUT/'inputs.json').exists():
        raise SystemExit('Frozen inputs already exist; use a new experiment directory.')
    db = sqlite3.connect(f'file:{ROOT / "data/mapwalker.sqlite3"}?mode=ro', uri=True)
    db.row_factory = sqlite3.Row
    rows = [dict(r) for r in db.execute('''SELECT p.*,t.source,t.z,t.x,t.y FROM pois p
        JOIN jobs j ON p.job_id=j.id JOIN tiles t ON j.tile_id=t.id
        JOIN algorithms a ON a.fingerprint=j.algorithm WHERE a.active=1 AND j.state='complete'
        AND p.kind='text' ORDER BY p.id''')]
    for row in rows:
        for field in ('box','details'):row[field]=json.loads(row[field])
    labels = {r['poi_id']:json.loads(r['payload']) for r in db.execute('''SELECT * FROM annotations a
        WHERE a.id=(SELECT max(b.id) FROM annotations b WHERE b.poi_id=a.poi_id)''')}
    # All labeled marks, including symbols, are needed to test false support.
    present={r['id'] for r in rows}
    for r in db.execute('''SELECT p.*,t.source,t.z,t.x,t.y FROM pois p JOIN jobs j ON p.job_id=j.id
        JOIN tiles t ON j.tile_id=t.id ORDER BY p.id'''):
        if r['id'] in labels and r['id'] not in present:
            row=dict(r)
            for field in ('box','details'):row[field]=json.loads(row[field])
            rows.append(row)
    write(OUT/'inputs.json', rows)
    write(OUT/'evaluation-labels.json', labels)
    catalog=list(csv.DictReader((DATA/'dtm-catalog.csv').open(encoding='utf-8-sig')))
    files=[]
    for name,url in [
        ('natural-places.csv','https://data.gov.tw/dataset/40456'),
        ('dtm-catalog.csv','https://data.gov.tw/dataset/176927'),
        ('taiwan-20m-2025.zip',catalog[-1]['連結網址']),
        ('DEM_tawiwan_V2025.tif',catalog[-1]['連結網址']),
    ]:
        path=DATA/name
        with path.open('rb') as f: digest=hashlib.file_digest(f,'sha256').hexdigest()
        files.append(dict(file=name,sha256=digest,bytes=path.stat().st_size,url=url))
    osm=sqlite3.connect(f'file:{ROOT / "data/osm/context.sqlite3"}?mode=ro',uri=True)
    osm.row_factory=sqlite3.Row
    snapshots=[dict(r) for r in osm.execute('SELECT * FROM requests WHERE raw_path IS NOT NULL ORDER BY key')]
    write(OUT/'osm-snapshots.json',snapshots)
    write(OUT/'provenance.json',dict(revision=subprocess.check_output(['git','rev-parse','HEAD'],cwd=ROOT,text=True).strip(),
        files=files,rows=len(rows),labels=len(labels),osm_snapshots=len(snapshots),
        inputs_sha256=hashlib.sha256((OUT/'inputs.json').read_bytes()).hexdigest(),
        labels_sha256=hashlib.sha256((OUT/'evaluation-labels.json').read_bytes()).hexdigest(),
        native_resolution_m=20,license='Government Data Open License, version 1.0',
        osm_license='© OpenStreetMap contributors, ODbL 1.0'))
    print('Frozen',len(rows),'automatic rows;',len(labels),'separate labels;',len(snapshots),'OSM snapshots')


if __name__=='__main__':main()
