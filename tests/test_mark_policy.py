from mapwalker.mark_policy import mark_regions
from mapwalker.display import priority
from mapwalker.region_model import compact_additions


def proposal(score=1.02,angle=0,scale=2,box=None):
    return dict(kind='text',text='',box=box or [90,100,140,150],score=score,repeating=False,
                details=dict(angle_degrees_ccw=angle,scale=scale,recognition='not attempted'))


def test_consistency_counts_distinct_rotations_not_scales_or_nearby_glyphs():
    p=proposal()
    output=mark_regions([p],[p,proposal(scale=3),proposal(angle=45),proposal(angle=90,score=.94),
                             proposal(angle=180,box=[180,100,230,150])])
    assert len(output)==1
    assert output[0]['details']['support_angles']==[0,45]
    assert output[0]['details']['support_scales']==[2,3]
    assert output[0]['details']['raw_peak']==1.02 and output[0]['score']==1
    assert output[0]['text']=='' and output[0]['box']==p['box']
    assert 'profile' not in p['details']  # Do not mutate frozen raw evidence.


def test_one_rotation_mark_is_retained_but_not_promoted_by_a_user_reading():
    p=proposal(score=.98)
    weak=mark_regions([p],[p])[0]
    strong=mark_regions([p],[p,proposal(angle=90)])[0]
    assert .5<priority(weak)<.74<priority(strong)
    assert priority({**weak,'text':'ウライ社','reading':'ウライ社','review':'confirmed'})==priority(weak)
    assert mark_regions([proposal(score=.94)],[proposal(score=.94)])==[]


def test_discovery_does_not_discard_an_adjacent_glyph_contained_in_a_shared_region():
    # A broad response is the only evidence for the upper mark. Containment NMS
    # would discard it after accepting the lower glyph and silently lose recall.
    lower=proposal(box=[109,310,159,368],score=1.03)
    shared=proposal(box=[92,253,154,362],score=1.016)
    output=mark_regions([lower,shared],[lower,shared])
    assert len(output)==2
    assert [p['box'] for p in output]==[lower['box'],shared['box']]


def test_original_scale_policy_still_preserves_its_existing_region():
    base=proposal(score=.43)
    assert compact_additions([base],[proposal(score=.9)])==[base]
