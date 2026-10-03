"""Run from the repository with python -m tools.backfill_vegetation.

Resume interrupted scans; completed runs reuse matching checks and retry errors.
The scan writes advisory evidence only and never classifies findings.
"""
import json,time
from mapwalker.paths import default_data
from mapwalker.db import Store
from mapwalker.vegetation_batch import VegetationBatch

if __name__=='__main__':
    data=default_data();batch=VegetationBatch(Store(data/'mapwalker.sqlite3'),data)
    last=[0]
    def progress(result):
        if time.monotonic()-last[0]>=10:
            print(json.dumps(result),flush=True);last[0]=time.monotonic()
    print(json.dumps(batch.scan(progress)),flush=True)
