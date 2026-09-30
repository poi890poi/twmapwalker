"""Versioned source-coverage preflight; detector identities stay unchanged."""
import hashlib
import json
import time
from pathlib import Path

import cv2
import numpy as np
from PIL import Image

from .sources import HISTORICAL
from .worker import Worker

POLICY_VERSION = 'blank-paper-1'
POLICY = hashlib.sha256(Path(__file__).read_bytes()).hexdigest()


def assess(image):
    gray = np.asarray(image.convert('L'))
    median, deviation = float(np.median(gray)), float(gray.std())
    strong = int(np.count_nonzero(gray.astype(float) < median - 60))
    background = cv2.GaussianBlur(gray.astype(np.float32), (0, 0), 3)
    residual = (background - gray > 8).astype(np.uint8)
    _, _, stats, _ = cv2.connectedComponentsWithStats(residual, 8)
    components = stats[1:]
    area = int(components[:, cv2.CC_STAT_AREA].max()) if len(components) else 0
    span = int(components[:, 2:4].max()) if len(components) else 0
    blank = median >= 180 and deviation <= 8 and strong < 3 and area < 32 and span < 12
    return dict(blank=bool(blank), median=median, std=deviation, strong_pixels=strong,
                largest_component=area, longest_component=span)


class CoverageWorker(Worker):
    def __init__(self, store, cache):
        super().__init__(store, cache)
        with store.connect() as db:
            db.execute('''CREATE TABLE IF NOT EXISTS historical_coverage (
                snapshot TEXT NOT NULL, source TEXT NOT NULL, z INTEGER NOT NULL,
                x INTEGER NOT NULL, y INTEGER NOT NULL, sha256 TEXT NOT NULL,
                policy TEXT NOT NULL, assessment TEXT NOT NULL, manifest TEXT NOT NULL,
                checked_at REAL NOT NULL,
                PRIMARY KEY(snapshot,source,z,x,y,sha256,policy))''')
            # A new coverage rule revisits only previous blank exclusions.
            # Prior assessments remain in historical_coverage and attempts.
            db.execute('''UPDATE jobs SET state='pending',available_at=0,attempts=0,
                token=NULL,lease_until=NULL,error=NULL
                WHERE state='complete' AND algorithm IN
                    (SELECT fingerprint FROM algorithms WHERE active=1)
                AND json_extract(telemetry,'$.skipped_reason')='blank_historical_map'
                AND COALESCE(json_extract(telemetry,'$.coverage.policy'),'')!=?
                AND NOT EXISTS (SELECT 1 FROM pois WHERE job_id=jobs.id)''', (POLICY,))

    def process(self, job):
        if job['source'] not in HISTORICAL:
            return super().process(job)
        start = time.perf_counter()
        spec = json.loads(job['spec'])
        if spec['snapshot'] != self.cache.root.name:
            raise ValueError('Worker imagery snapshot does not match job')
        path, manifest, cached = self.cache.get(job['source'], job['z'], job['x'], job['y'])
        identity = (spec['snapshot'],job['source'],job['z'],job['x'],job['y'],manifest['sha256'],POLICY)
        with self.store.connect() as db:
            row = db.execute('''SELECT assessment FROM historical_coverage
                WHERE snapshot=? AND source=? AND z=? AND x=? AND y=? AND sha256=? AND policy=?''', identity).fetchone()
        if row:
            assessment = json.loads(row['assessment'])
        else:
            with Image.open(path) as image:
                assessment = assess(image)
            with self.store.connect() as db:
                db.execute('INSERT OR IGNORE INTO historical_coverage VALUES(?,?,?,?,?,?,?,?,?,?)',
                           (*identity,json.dumps(assessment),json.dumps(manifest),time.time()))
        coverage = dict(**assessment, policy=POLICY, version=POLICY_VERSION,
                        sha256=manifest['sha256'], assessment_cached=bool(row), tile_cached=cached)
        preflight_ms = (time.perf_counter()-start)*1000
        if assessment['blank']:
            telemetry = dict(skipped_reason='blank_historical_map',coverage=coverage,
                coverage_ms=preflight_ms,total_ms=preflight_ms,io_ms=preflight_ms,decode_ms=0,
                model_init_ms=0,detect_ms=0,filter_ms=0,proposals=0,owned=0,candidates=0,excluded=0)
            return [], telemetry, [manifest]
        pois, telemetry, inputs = super().process(job)
        telemetry['coverage'] = coverage
        telemetry['coverage_ms'] = preflight_ms
        telemetry['total_ms'] += preflight_ms
        return pois, telemetry, inputs
