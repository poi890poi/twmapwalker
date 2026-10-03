"""Causal and geometric invariants for predicting contours across a hidden target."""
import unittest
import numpy as np
from PIL import Image,ImageDraw
from tools.contour_curve_features import infer_curves,extract
from tools.contour_curve_features_v2 import infer_curves as infer_v2,extract as extract_v2,chains as chains_v2


def scene(curve=True):
    im=Image.new('L',(192,192),240);draw=ImageDraw.Draw(im)
    for offset in range(30,180,20):
        points=[(x,offset+round(.0015*(x-96)**2 if curve else 0)) for x in range(8,185)]
        draw.line(points,fill=35,width=3)
    return im


class CurveTests(unittest.TestCase):
    def test_target_cannot_steer_predicted_contours(self):
        im=scene();box=[78,78,114,114]
        first,tube,_=infer_curves(im,box)
        changed=im.copy();ImageDraw.Draw(changed).rectangle((78,78,113,113),fill=0)
        second,other,_=infer_curves(changed,box)
        self.assertEqual(first,second)
        np.testing.assert_array_equal(tube,other)

    def test_curves_explain_contour_ink_but_leave_added_stroke(self):
        im=scene();box=[78,78,114,114]
        _,plain=extract(im,box)
        changed=im.copy();ImageDraw.Draw(changed).line((95,82,95,110),fill=0,width=3)
        _,marked=extract(changed,box)
        self.assertTrue(plain['available'])
        self.assertGreater(plain['explained_ink_fraction'],.8)
        self.assertGreater(marked['residual_ink_fraction'],plain['residual_ink_fraction']+.15)

    def test_isolated_mark_has_no_contour_explanation(self):
        im=Image.new('L',(192,192),240);ImageDraw.Draw(im).ellipse((82,82,110,110),outline=0,width=3)
        _,result=extract(im,[78,78,114,114])
        self.assertFalse(result['available'])
        self.assertEqual(result['explained_ink_fraction'],0)

    def test_blank_image_is_finite_and_unavailable(self):
        vector,result=extract(Image.new('L',(192,192),255),[78,78,114,114])
        self.assertFalse(result['available'])
        self.assertTrue(np.isfinite(vector).all())

    def test_continuous_variant_preserves_causal_curve_and_residual_checks(self):
        im=scene();box=[78,78,114,114]
        changed=im.copy();ImageDraw.Draw(changed).line((95,82,95,110),fill=0,width=3)
        first,tube,_=infer_v2(im,box);second,other,_=infer_v2(changed,box)
        self.assertEqual(first,second);np.testing.assert_array_equal(tube,other)
        _,plain=extract_v2(im,box);_,marked=extract_v2(changed,box)
        self.assertTrue(plain['available']);self.assertGreater(plain['explained_ink_fraction'],.8)
        self.assertGreater(marked['residual_ink_fraction'],plain['residual_ink_fraction']+.15)

    def test_continuous_variant_bridges_short_break_but_not_large_break(self):
        mask=np.zeros((80,100),bool);mask[40,10:50]=True;mask[40,52:90]=True
        self.assertGreater(max(map(len,chains_v2(mask))),70)
        mask[40,48:57]=False
        self.assertLess(max(map(len,chains_v2(mask))),50)

    def test_continuous_variant_follows_through_t_junction(self):
        mask=np.zeros((80,100),bool);mask[40,10:90]=True;mask[10:40,50]=True
        self.assertGreaterEqual(max(map(len,chains_v2(mask))),78)


if __name__=='__main__':unittest.main()
