import json
import threading
import time

import numpy as np

from .detectors import TextDetector, developed_mask, filter_proposals, symbol_proposals, specs
from .geo import pixel_lonlat
from .junctions import junction_proposals
from .trails import trail_proposals
from .angled import angled_text_proposals


class Worker:
    def __init__(self, store, cache):
        self.store = store
        self.cache = cache
        self.stop = threading.Event()
        self.ocr = None
        self.regions = None
        self.fingerprints = [s['fingerprint'] for s in specs()]

    def process(self, job):
        start = time.perf_counter()
        spec = json.loads(job['spec'])
        config = spec['config']
        if spec['snapshot'] != self.cache.root.name:
            raise ValueError('Worker imagery snapshot does not match job')
        history, hist_manifest, hist_times = self.cache.mosaic(job['source'],job['z'],job['x'],job['y'],config['pad'])
        modern, modern_manifest, modern_times = self.cache.mosaic('EMAP',job['z'],job['x'],job['y'],config['pad'])
        # Blank / uniform source responses cannot establish that no POI exists.
        if np.asarray(history).std() < 2 or np.asarray(modern).std() < 2:
            raise ValueError('Uniform/no-data source image; result not published')
        tick = time.perf_counter()
        init_ms = 0
        if job['name'] in ('text','angled-text'):
            if self.ocr is None:
                self.ocr = TextDetector()
                init_ms = (time.perf_counter()-tick)*1000
                tick = time.perf_counter()
            proposals = self.ocr(history, config) if job['name']=='text' else angled_text_proposals(history,config,self.ocr)
        elif job['name']=='symbols':
            proposals = symbol_proposals(history, config)
        elif job['name']=='junctions':
            proposals = junction_proposals(history, config)
        elif job['name']=='trails':
            proposals = trail_proposals(history, config)
        elif job['name']=='text-regions':
            from .regions import RegionDetector
            if self.regions is None:
                self.regions = RegionDetector(spec)
            proposals = self.regions(history, config)
        else:
            raise ValueError(f'No implementation for algorithm {job["name"]}')
        detect_ms = (time.perf_counter()-tick)*1000
        tick = time.perf_counter()
        mask = developed_mask(modern,config)
        pois = filter_proposals(proposals,mask,config)
        for poi in pois:
            x0,y0,x1,y1 = poi['box']
            poi['lon'],poi['lat'] = pixel_lonlat(job['z'],job['x'],job['y'],(x0+x1)/2,(y0+y1)/2)
            if poi['kind']=='trail':
                path=poi['details']['pixel_path']
                poi['details']['geometry']=dict(type='LineString',coordinates=[
                    pixel_lonlat(job['z'],job['x'],job['y'],px-config['pad'],py-config['pad']) for px,py in path])
        telemetry = dict(io_ms=hist_times['io_ms']+modern_times['io_ms'],
                         decode_ms=hist_times['decode_ms']+modern_times['decode_ms'],
                         model_init_ms=init_ms, detect_ms=detect_ms, filter_ms=(time.perf_counter()-tick)*1000,
                         total_ms=(time.perf_counter()-start)*1000,
                         proposals=len(proposals),owned=len(pois),
                         candidates=sum(p['disposition']=='candidate' for p in pois),
                         excluded=sum(p['disposition']=='excluded' for p in pois))
        if job['name']=='text-regions':
            telemetry['region_backend']=self.regions.last_timing
            telemetry['detect_includes_isolated_process_startup']=True
        return pois, telemetry, hist_manifest+modern_manifest

    def once(self):
        job = self.store.claim(fingerprints=self.fingerprints)
        if job is None:
            return False
        done = threading.Event()
        def keepalive():
            while not done.wait(20):
                if not self.store.heartbeat(job):
                    return
        heartbeat = threading.Thread(target=keepalive,daemon=True)
        heartbeat.start()
        try:
            output = self.process(job)
            self.store.finish(job,*output)
        except Exception as error:
            self.store.fail(job,f'{type(error).__name__}: {error}')
        finally:
            done.set()
            heartbeat.join(timeout=1)
        return True

    def run(self):
        while not self.stop.is_set():
            if not self.once():
                self.stop.wait(1)
