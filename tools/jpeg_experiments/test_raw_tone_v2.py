"""Behaviour checks for explicit scene-exposure film tone experiments."""

from __future__ import annotations

import importlib

import numpy as np
import pytest


def _renderer(name):
    try:
        module = importlib.import_module("raw_tone_v2")
    except ModuleNotFoundError:
        pytest.fail("The RAW film-tone renderer must be implemented")
    function = getattr(module, name, None)
    assert callable(function), f"RAW tone renderer {name} must be implemented"
    return function


def _neutral(levels):
    return np.repeat(np.asarray(levels, dtype=np.float32)[..., None], 3, axis=-1)


def test_standard_reference_has_contrast_and_a_real_highlight_shoulder():
    render = _renderer("render_reference_standard")
    levels = _neutral([0, .01, .05, .18, .5, 1, 2, 4])
    out = render(levels)[:, 0]
    assert out[0] == 0
    assert .44 < out[3] < .53
    assert out[4] - out[2] > .45
    assert .70 < out[5] < out[6] < out[7] < 1
    assert out[6] - out[5] > .025


def test_styles_change_shadows_contrast_and_shoulders_by_visible_amounts():
    render = _renderer("render_film_tone")
    standard = _renderer("render_reference_standard")
    scene = _neutral([0, .01, .05, .18, .5, 1, 2, 4])
    reference = standard(scene)[:, 0]
    negative = render(scene, style="negative")[:, 0]
    fade = render(scene, style="fade")[:, 0]
    contrast = render(scene, style="contrast")[:, 0]
    # Catch a renderer whose strength only changes already-bright RAW pixels.
    assert negative[2] < reference[2] - .05
    assert negative[4] > reference[4] + .07
    assert .07 < fade[0] < fade[1] < fade[2]
    assert fade[-1] < reference[-1] - .05
    assert contrast[4] - contrast[2] > reference[4] - reference[2] + .15


@pytest.mark.parametrize("style", ["negative", "fade", "contrast"])
def test_strength_zero_is_common_reference_and_two_goes_beyond_one(style):
    render = _renderer("render_film_tone")
    scene = _neutral(np.geomspace(.001, 4, 101))
    baseline = _renderer("render_reference_standard")(scene, exposure=1.3)
    np.testing.assert_array_equal(render(scene, style, exposure=1.3, strength=0), baseline)
    one = render(scene, style, exposure=1.3, strength=1)
    two = render(scene, style, exposure=1.3, strength=2)
    assert np.max(np.abs(one - baseline)) > .07
    assert np.max(np.abs(two - one)) > .04


@pytest.mark.parametrize("style", ["negative", "fade", "contrast"])
@pytest.mark.parametrize("strength", [0, .5, 1, 1.5, 2])
def test_neutral_response_is_monotone_bounded_and_nonmutating(style, strength):
    render = _renderer("render_film_tone")
    scene = _neutral(np.concatenate(([0], np.geomspace(1e-8, 1e8, 800))))
    saved = scene.copy()
    scene.flags.writeable = False
    out = render(scene, style, strength=strength)
    assert out.dtype == np.float32 and out.shape == scene.shape
    assert np.isfinite(out).all() and out.min() >= 0 and out.max() <= 1
    assert np.all(np.diff(out[:, 0]) >= 0)
    np.testing.assert_array_equal(out[:, 0], out[:, 1])
    np.testing.assert_array_equal(out[:, 1], out[:, 2])
    np.testing.assert_array_equal(scene, saved)


def test_exposure_is_explicit_deterministic_and_has_no_image_based_matching():
    render = _renderer("render_film_tone")
    scene = np.array([[[.02, .07, .15], [.2, .4, 1.2]]], np.float32)
    np.testing.assert_allclose(render(scene, exposure=2), render(scene * 2), atol=1e-7)
    # Surrounding the same pixel with bright pixels must not change its tone.
    extended = np.concatenate((scene, np.full_like(scene, 3)), axis=1)
    np.testing.assert_array_equal(render(scene), render(extended)[:, :2])


@pytest.mark.parametrize("kwargs", [{"strength": -.1}, {"strength": 2.1},
                                         {"strength": float("nan")},
                                         {"exposure": -1}, {"exposure": float("inf")},
                                         {"style": "unknown"}])
def test_invalid_controls_are_rejected(kwargs):
    with pytest.raises(ValueError):
        _renderer("render_film_tone")(_neutral([.18]), **kwargs)


@pytest.mark.parametrize("scene", [np.array([[0, -1, 0]], np.float32),
                                   np.array([[0, np.nan, 0]], np.float32),
                                   np.zeros((1, 4), np.float32), np.zeros((0, 3), np.float32)])
def test_invalid_scene_data_is_rejected(scene):
    with pytest.raises(ValueError):
        _renderer("render_film_tone")(scene)
