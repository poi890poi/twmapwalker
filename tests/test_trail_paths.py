import numpy as np
import pytest
from PIL import Image, ImageDraw
from mapwalker.detectors import CONFIG, filter_proposals
from mapwalker.trail_paths import supported_runs
from mapwalker.trails import trail_proposals


def test_projection_order_cannot_bridge_unconnected_dash_branches():
    # Projection interleaves two supported chains. The middle jump is not a trail.
    graph=[{1},{0,2},{1},{4},{3,5},{4}]
    assert supported_runs([0,1,2,3,4,5],graph)==[[0,1,2],[3,4,5]]
    assert supported_runs([],graph)==[]
    assert supported_runs([0,3,1,4,2,5],graph)==[[0],[3],[1],[4],[2],[5]]


def test_supported_trail_keeps_geometry_and_survives_owner_filter():
    image=Image.new('RGB',(384,384),'white');draw=ImageDraw.Draw(image)
    for x in [110,130,150,170]:
        draw.rectangle((x,179,x+8,182),fill='black')
    trails=trail_proposals(image,CONFIG)
    assert len(trails)==1
    path=trails[0]['details']['pixel_path']
    assert len(path)==4
    assert all(np.linalg.norm(np.array(a)-b)==pytest.approx(20) for a,b in zip(path,path[1:]))
    owned=filter_proposals(trails,np.zeros((384,384),bool))
    assert len(owned)==1 and owned[0]['disposition']=='candidate'
    assert owned[0]['details']['pixel_path']==path


