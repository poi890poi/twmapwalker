import json

from mapwalker.writing_direction import infer_direction
from test_names import client,BOUNDS


def row(pid,text,box,**details):
    return dict(id=pid,text=text,box=box,details=details,x=54896,y=28092,z=16)


def test_whole_reading_and_missing_characters_use_raw_glyph_order():
    raw=row(1,'溪後桶',[10,10,100,30])
    assert infer_direction('桶後溪',[raw])['direction']=='rtl'
    assert infer_direction('溪後桶',[raw])['direction']=='ltr'
    partial=row(1,'社烏',[10,10,80,30])
    inferred=infer_direction('烏來社',[partial])
    assert inferred['direction']=='rtl' and inferred['matched_glyphs']==['烏','社']
    assert infer_direction('烏?社',[partial])['direction']=='rtl'


def test_group_order_uses_geometry_not_click_order_and_handles_tile_edges():
    left=row(1,'社',[220,10,240,30])
    right={**row(2,'烏',[20,10,40,30]),'x':54897}
    assert infer_direction('烏來社',[right,left])['direction']=='rtl'
    assert infer_direction('烏來社',[left,right])['direction']=='rtl'
    # Same actual position at a different tile zoom.
    higher={**right,'x':right['x']*2,'y':right['y']*2,'z':17,'box':[40,20,80,60]}
    assert infer_direction('烏來社',[left,higher])['direction']=='rtl'


def test_vertical_rotated_and_upside_down_rows():
    assert infer_direction('烏來社',[row(1,'社來烏',[10,10,30,100])])['direction']=='vertical'
    assert infer_direction('烏來社',[row(1,'烏',[10,10,30,30]),row(2,'社',[10,80,30,100])])['direction']=='vertical'
    # Original-image polygon after undoing the OCR rotation (leftward baseline).
    upside=row(1,'烏來社',[10,10,100,30],polygon=[[100,30],[10,30],[10,10],[100,10]])
    assert infer_direction('烏來社',[upside])['direction']=='rtl'
    assert infer_direction('社來烏',[upside])['direction']=='ltr'


def test_abstains_on_weak_ambiguous_and_conflicting_evidence():
    assert infer_direction('烏來社',[row(1,'社',[10,10,30,30])])['direction']=='unknown'
    assert infer_direction('山山',[row(1,'山山',[10,10,80,30])])['direction']=='unknown'
    assert infer_direction('???',[row(1,'烏來社',[10,10,100,30])])['direction']=='unknown'
    assert infer_direction('烏來社',[row(1,'甲乙',[10,10,80,30])])['direction']=='unknown'
    assert infer_direction('烏來社',[row(1,'烏烏社',[10,10,100,30])])['direction']=='unknown'
    conflicting=[row(1,'烏',[10,10,30,30]),row(2,'來',[90,10,110,30]),row(3,'社',[50,10,70,30])]
    assert infer_direction('烏來社',conflicting)['reason']=='conflicting-glyph-order'
    duplicates=[row(1,'烏',[10,10,30,30]),row(2,'烏',[60,10,80,30]),row(3,'社',[100,10,120,30])]
    assert infer_direction('烏來社',duplicates)['direction']=='unknown'
    assert infer_direction('烏社',[row(1,'烏',[10,10,30,30]),row(2,'社',[10,10,30,30])])['direction']=='unknown'
    assert infer_direction('שלום',[row(1,'שלום',[10,10,100,30])])['direction']=='unknown'
    assert infer_direction('שלום',[row(1,'ש',[90,10,110,30]),row(2,'ם',[10,10,30,30])])['direction']=='rtl'


def test_additional_mixed_fragment_and_diagonal_cases():
    # Independently arranged pieces: eastern glyphs begin a historical RTL label.
    rows=[row(9,'溪',[10,15,30,35]),row(3,'東山',[60,15,120,35])]
    assert infer_direction('山東溪',rows)['direction']=='rtl'
    # A diagonal pair does not justify a horizontal or vertical classification.
    assert infer_direction('甲乙',[row(1,'甲',[10,10,30,30]),row(2,'乙',[70,70,90,90])])['direction']=='unknown'


def test_preview_is_read_only_save_recomputes_and_manual_override_survives(client):
    c,store=client;pid=store.pois(BOUNDS)['items'][0]['id']
    with store.connect() as db:
        db.execute('UPDATE pois SET text=?,box=?,details=? WHERE id=?',('溪後桶',json.dumps([10,10,100,30]),'{}',pid))
    url=f'/api/pois/{pid}'
    preview=c.post(url+'/writing-direction',json=dict(label='桶後溪',member_ids=[pid]))
    assert preview.status_code==200 and preview.json()['direction']=='rtl'
    assert store.poi(pid)['annotations']==[]
    payload=dict(ground_truth='桶後溪',map_direction='auto',sync_reading=True,classification='poi')
    saved=c.post(url+'/annotation',json=payload).json()['annotation']
    assert saved['map_direction']=='rtl' and saved['direction_source']=='automatic'
    assert saved['direction_evidence']==preview.json()
    assert store.poi(pid)['text']=='溪後桶' and store.poi(pid)['reading']=='桶後溪'
    payload['map_direction']='ltr'
    saved=c.post(url+'/annotation',json=payload).json()['annotation']
    assert saved['map_direction']=='ltr' and saved['direction_source']=='manual'
    assert 'direction_evidence' not in saved
    assert c.post(url+'/writing-direction',json=dict(label='桶後溪',member_ids=[999999])).status_code==400


def test_removing_direction_evidence_clears_automatic_result(client):
    c,store=client
    a,b=[p['id'] for p in store.pois(BOUNDS)['items'][:2]]
    with store.connect() as db:
        for pid,text,box in [(a,'社',[10,10,30,30]),(b,'烏',[80,10,100,30])]:
            db.execute('UPDATE pois SET text=?,box=?,details=? WHERE id=?',(text,json.dumps(box),'{}',pid))
    payload=dict(ground_truth='烏來社',map_direction='auto',member_ids=[a,b],sync_reading=True)
    url=f'/api/pois/{a}/annotation'
    assert c.post(url,json=payload).json()['annotation']['map_direction']=='rtl'
    assert store.poi(b)['annotation']['map_direction']=='rtl'
    payload['member_ids']=[a]
    saved=c.post(url,json=payload).json()['annotation']
    assert saved['map_direction']=='unknown'
    assert saved['direction_evidence']['reason']=='insufficient-glyph-evidence'
    assert store.poi(b)['annotation']['map_direction']=='rtl'
