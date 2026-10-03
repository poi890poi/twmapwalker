"""Read-only availability and potential-rescue audit; no fitted fusion or new labels."""
import json
import sqlite3
import time
from collections import Counter
from .contour_learner_data import ROOT,read,write,sha
from .local_mark_data import OUT,PREV
from mapwalker.evidence_sources import LocalEvidence
from mapwalker.multi_evidence import analyze
from mapwalker.osm import cell,normalize,distance_m


def main():
    write(OUT/'modal-contract.json',dict(scope='Complementary feasibility audit of existing external evidence; not the conditional trained fusion stage and not independent model validation.',
        inference='Automatic OCR strings/details and detector coordinates only. Cached OSM,local MOI natural-name gazetteer and installed native DTM. No annotations or saved OSM links enter inference.',
        signals='Unambiguous name-supported candidate; weaker numeric/elevation compatibility. Missing evidence neutral; geographic drift accommodated by existing1000m search; absence cannot certify noise.',
        evaluation='After extraction, join previous frozen visual flags and reference labels to count potentially rescued protected flags and falsely supported contour targets. No threshold fitting or fresh data use.'))
    rows=read(OUT/'training.json')+read(OUT/'guards.json')+read(OUT/'challenge.json')
    db=sqlite3.connect('file:'+str(ROOT/'data/mapwalker.sqlite3').replace('\\','/')+'?mode=ro',uri=True);db.row_factory=sqlite3.Row
    osm=sqlite3.connect('file:'+str(ROOT/'data/osm/context.sqlite3').replace('\\','/')+'?mode=ro',uri=True);osm.row_factory=sqlite3.Row
    sources=LocalEvidence(ROOT/'data');cache={};results=[];snapshots={};times=[]
    for r in rows:
        if not str(r['id']).isdigit():results.append(dict(id=r['id'],state='reference-control',readings=[],name_support=False,numeric_support=False));continue
        row=db.execute('SELECT id,text,details,lon,lat FROM pois WHERE id=?',(r['id'],)).fetchone()
        if row is None:results.append(dict(id=r['id'],state='missing-record',readings=[],name_support=False,numeric_support=False));continue
        poi=dict(row);poi['details']=json.loads(poi['details']);key,_,_=cell(poi['lon'],poi['lat'])
        if key not in cache:
            snapshot=osm.execute('SELECT * FROM requests WHERE key=? AND raw_path IS NOT NULL',(key,)).fetchone();features=[]
            if snapshot:
                snapshot=dict(snapshot);path=ROOT/'data/osm'/snapshot['raw_path'];assert sha(path)==snapshot['digest']
                features=normalize(read(path));snapshots[key]=snapshot
            cache[key]=features
        start=time.perf_counter();nearby=[f for f in cache[key] if distance_m(f['geometry'],poi['lon'],poi['lat'])<=1000]
        gaz,coverage=sources.nearby(poi['lon'],poi['lat']);value=analyze(poi,nearby+gaz,sources,coverage)
        terrain=sources.point(poi['lon'],poi['lat']);times.append((time.perf_counter()-start)*1000)
        results.append(dict(id=r['id'],state=value['state'],readings=value['raw_readings'],name_support=value['state']=='name-supported',
            numeric_support=any(c['numeric_compatible'] for c in value['candidates']),osm_cached=key in snapshots,
            gazetteer_available=coverage['state']=='available',terrain=terrain,automatic_input=poi,candidates=value['candidates']))
    db.close();osm.close();write(OUT/'modal-features.json',results)
    # Evaluation joins only after the signal artifact is saved.
    old=read(PREV/'development-predictions.json')['dino-structure-rf']
    flags=old['oof']+old['guards']+read(PREV/'holdout-evaluation.json')['rows'];assert len(flags)==len(results)
    audit=[]
    for r,f,e in zip(rows,flags,results):
        assert str(r['id'])==str(f['id'])==str(e['id'])
        audit.append(dict(id=r['id'],label=r['label'],negative=r['negative'],visual_flag=f['reject'],name_support=e['name_support'],numeric_support=e['numeric_support']))
    summary=dict(count=len(rows),states=dict(Counter(r['state'] for r in results)),
        automatic_readings=sum(bool(r['readings']) for r in results),osm_cached=sum(r.get('osm_cached',False) for r in results),
        gazetteer_available=sum(r.get('gazetteer_available',False) for r in results),terrain_states=dict(Counter(r.get('terrain',{}).get('state','not-queried') for r in results)),
        native_terrain=sources.terrain_status(),
        name_supported_protected=sum(r['name_support'] and not r['negative'] for r in audit),name_supported_contours=sum(r['name_support'] and r['negative'] for r in audit),
        prior_protected_flags=sum(r['visual_flag'] and not r['negative'] for r in audit),
        potential_name_rescues=sum(r['visual_flag'] and not r['negative'] and r['name_support'] for r in audit),
        potential_numeric_rescues=sum(r['visual_flag'] and not r['negative'] and r['numeric_support'] for r in audit),
        milliseconds=times,scope='Existing-data availability/potential rescue, not trained multimodal model accuracy; no fresh holdout use',
        feature_sha256=sha(OUT/'modal-features.json'),code_sha256=sha(ROOT/'tools/local_mark_modal_audit.py'))
    write(OUT/'modal-summary.json',summary);write(OUT/'modal-audit.json',audit);write(OUT/'modal-snapshots.json',snapshots)
    print(json.dumps({k:v for k,v in summary.items() if k not in ('milliseconds','native_terrain')},indent=2),flush=True)


if __name__=='__main__':main()
