"""Repeatable read-only sample timings and isolated scale fixture for the viewer."""
import json
import sqlite3
import sys
import time
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from mapwalker.db import Store


def timed(store,bbox,**kwargs):
    timings=[]
    for _ in range(5):
        start=time.perf_counter();result=store.pois(bbox,limit=50,zoom=15,**kwargs)
        timings.append(round((time.perf_counter()-start)*1000,2))
    data=result['map']
    represented=sum(p['count'] for p in data['items']) if data['mode']=='groups' else len(data['items'])
    assert represented==result['total']==data['total']
    return dict(total=result['total'],map_elements=len(data['items']),mode=data['mode'],
                response_bytes=len(json.dumps(result).encode()),milliseconds=timings)


def main():
    out=ROOT/'evidence/viewer'
    baseline=ROOT/'data/viewer-baseline.sqlite3'
    # Verify all historical rows, independent readings, and detector identities.
    with sqlite3.connect(ROOT/'data/mapwalker.sqlite3') as db:
        db.execute('ATTACH DATABASE ? AS baseline',(str(baseline),))
        preserved={table:db.execute(f'SELECT COUNT(*) FROM (SELECT * FROM baseline.{table} EXCEPT SELECT * FROM main.{table})').fetchone()[0]
                   for table in ['pois','jobs','reviews','readings','algorithms','tiles']}
    assert not any(preserved.values()),preserved
    store=Store(baseline)
    report=dict(missing_or_changed_baseline_rows=preserved,
                sample=timed(store,(118,21.5,123,26.5),source='JM50K_1924_new'))
    # Separate synthetic data; never publish fabricated findings into production.
    fixture=Store(ROOT/'data/viewer-scale-fixture.sqlite3')
    spec=dict(fingerprint='viewer-scale-fixture',name='fixture',version='test',config={},snapshot='test')
    fixture.register([spec]);fixture.enqueue('JM50K_1924_new',[(16,54896,28092)])
    if job:=fixture.claim():
        rows=[dict(kind='symbol',text='',score=.5,lon=118.1+(i%400)*.01,
                   lat=21.6+(i//400)*.018,box=[1,1,5,5],disposition='candidate') for i in range(100000)]
        fixture.finish(job,rows,{},[])
    report['synthetic_100000']=timed(fixture,(118,21.5,123,26.5),source='JM50K_1924_new')
    report['limits']='Server query time only; excludes HTTP, image fetch, decoding and browser rendering. Synthetic fixture is not detection evidence.'
    (out/'verification.json').write_text(json.dumps(report,indent=2),encoding='utf-8')
    print(json.dumps(report,indent=2))


if __name__=='__main__':main()
