import pytest
from tools.build_batongguan_review import build


def source(members):
    return {'elements':[{'type':'relation','id':13678191,'tags':{'name':'八通關古道'},'members':[{'type':'way','ref':i} for i in members]}]}


def way(oid,geometry):
    return {'type':'way','id':oid,'tags':{'highway':'service'},'geometry':geometry}


def test_exact_route_members_include_unnamed_non_path_ways_and_exclude_nonmembers():
    g=[{'lon':120.94,'lat':23.55},{'lon':120.941,'lat':23.55}]
    result=build(source([123]),{'elements':[way(123,g),way(456,g)]})
    assert {s['osm_way'] for s in result['segments']}=={123}
    assert result['segments'][0]['highway']=='service'


def test_missing_route_member_fails_instead_of_showing_partial_route_as_complete():
    with pytest.raises(AssertionError,match='Missing members'):
        build(source([123]),{'elements':[]})


def test_geometry_gaps_are_not_bridged():
    g=[{'lon':120.94,'lat':23.55},{'lon':120.941,'lat':23.55},None,
       {'lon':121.04,'lat':23.55},{'lon':121.041,'lat':23.55}]
    result=build(source([123]),{'elements':[way(123,g)]})
    assert len(result['segments'])==2
    assert all(s['length_m']<150 for s in result['segments'])
