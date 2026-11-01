import numpy as np
import pytest
from colour.difference import delta_E_CIE2000
from perceptual_v2 import de00, fixed_masks, measure, normal_view, summarize

def test_sharma_reference_pair():
    assert float(delta_E_CIE2000([50, 2.6772, -79.7751], [50, 0, -82.7485])) == pytest.approx(2.0425, abs=.0001)

def test_identity_and_known_white_black():
    a = np.array([[[0, 0, 0], [1, 1, 1], [.2, .5, .8]]], dtype=np.float32)
    assert np.max(de00(a, a)) == 0
    assert de00(a[:, :1], a[:, 1:2]).item() == pytest.approx(100, abs=.01)

def test_fixed_masks_reused_through_sweep():
    a = np.array([[[.2, .6, .2], [.2, .3, .8], [.8, .2, .1]]], dtype=np.float32)
    masks = fixed_masks(a)
    counts = {k: v.sum() for k, v in masks.items()}
    measure(a, np.ones_like(a), masks)
    assert counts == {k: v.sum() for k, v in masks.items()}
    assert counts['colour'] == 3

def test_empty_target_is_explicit_and_json_safe():
    assert summarize(np.zeros((2, 2)), np.zeros((2, 2), bool))['mean_de00'] is None

def test_float_resize_preserves_sub_codevalue_delta():
    a = np.full((1000, 1000, 3), .5, dtype=np.float32)
    b = a + .0001
    assert np.mean(normal_view(b) - normal_view(a)) == pytest.approx(.0001, abs=1e-7)

def test_bloom_mask_really_includes_surrounding_pixels():
    a = np.zeros((100,100,3),dtype=np.float32)
    a[45:55,45:55]=1
    assert fixed_masks(a)['highlights_and_surround'].sum()>100
