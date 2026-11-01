"""Behaviour checks for real-headroom RAW rendering; no private fixture required."""

from __future__ import annotations

import os
from pathlib import Path

import numpy as np
import pytest

import raw_ops


def _renderer(name):
    function = getattr(raw_ops, name, None)
    assert callable(function), f"RAW renderer {name} must be implemented"
    return function


def test_baseline_is_standard_srgb_and_clips_scene_highlights():
    render = _renderer("render_baseline")
    linear = np.repeat(np.array([0.0, 0.0031308, 0.18, 1.0, 2.0], np.float32)[None, :, None], 3, axis=-1)
    out = render(linear)
    np.testing.assert_allclose(out[0, :, 0], [0.0, 0.04044994, 0.4613561, 1.0, 1.0], atol=2e-6)
    assert out.dtype == np.float32


def test_protected_keeps_middles_neutral_and_retains_highlight_separation():
    protect = _renderer("render_protected")
    baseline = _renderer("render_baseline")
    levels = np.array([0.0, 0.01, 0.18, 0.3, 0.5, 0.75, 1.0, 1.5, 2.0, 4.0], np.float32)
    ramp = np.repeat(levels[None, :, None], 3, axis=-1)
    out = protect(ramp)
    np.testing.assert_allclose(out[..., 0], out[..., 1], atol=1e-7)
    np.testing.assert_allclose(out[..., 1], out[..., 2], atol=1e-7)
    np.testing.assert_allclose(out[:, :5], baseline(ramp)[:, :5], atol=1e-7)
    assert np.all(np.diff(out[0, :, 0]) > 0)
    assert np.all(np.diff(out[0, 6:, 0]) > 0.002)
    assert out.min() == 0 and out.max() < 1.0


def test_zero_protection_is_baseline_and_full_protection_preserves_linear_hue_ratios():
    protect = _renderer("render_protected")
    baseline = _renderer("render_baseline")
    scene = np.array([[[2.0, 1.0, 0.5], [0.2, 0.4, 0.1]]], np.float32)
    np.testing.assert_array_equal(protect(scene, strength=0), baseline(scene))
    encoded = protect(scene, strength=1)
    recovered = np.where(encoded <= 0.04045, encoded / 12.92, ((encoded + 0.055) / 1.055) ** 2.4)
    np.testing.assert_allclose(recovered[0, 0] / recovered[0, 0, 0], [1, 0.5, 0.25], rtol=2e-6)


@pytest.mark.parametrize("name", ["render_baseline", "render_protected", "render_recipe"])
def test_renderers_are_finite_bounded_nonmutating_and_respect_exposure(name):
    render = _renderer(name)
    scene = np.random.default_rng(78).uniform(0, 5, (16, 17, 3)).astype(np.float32)
    saved = scene.copy()
    scene.flags.writeable = False
    out = render(scene, exposure=1.3)
    np.testing.assert_array_equal(scene, saved)
    assert np.isfinite(out).all() and out.min() >= 0 and out.max() <= 1
    assert out.dtype == np.float32 and out.shape == scene.shape
    np.testing.assert_array_equal(render(scene, exposure=0), np.zeros_like(scene))


def test_recipe_warmth_and_tint_have_intended_direction_without_moving_black():
    recipe = _renderer("render_recipe")
    protect = _renderer("render_protected")
    neutral = np.array([[[0, 0, 0], [0.18, 0.18, 0.18]]], np.float32)
    warm = recipe(neutral, warmth=0.12)
    cool = recipe(neutral, warmth=-0.12)
    magenta = recipe(neutral, warmth=0, tint=0.12)
    assert warm[0, 1, 0] > warm[0, 1, 1] > warm[0, 1, 2]
    assert cool[0, 1, 2] > cool[0, 1, 1] > cool[0, 1, 0]
    assert magenta[0, 1, 0] > magenta[0, 1, 1]
    assert magenta[0, 1, 2] > magenta[0, 1, 1]
    np.testing.assert_array_equal(warm[0, 0], [0, 0, 0])
    np.testing.assert_allclose(recipe(neutral, warmth=0, tint=0), protect(neutral), atol=1e-7)


def test_white_balance_only_has_no_highlight_shoulder_and_preserves_neutral_identity():
    white_balance = _renderer("render_white_balance")
    baseline = _renderer("render_baseline")
    recipe = _renderer("render_recipe")
    scene = np.array([[[0, 0, 0], [.18, .18, .18], [2, 2, 2]]], np.float32)
    saved = scene.copy()
    np.testing.assert_array_equal(white_balance(scene, warmth=0, tint=0), baseline(scene))
    warm = white_balance(scene, warmth=.12)
    assert warm[0, 1, 0] > warm[0, 1, 1] > warm[0, 1, 2]
    np.testing.assert_array_equal(warm[0, 2], baseline(scene)[0, 2])
    assert np.all(recipe(scene, warmth=.12)[0, 2] < 1)
    np.testing.assert_array_equal(scene, saved)


@pytest.mark.parametrize("name", ["render_baseline", "render_protected", "render_recipe"])
def test_nonfinite_scene_or_exposure_is_rejected(name):
    render = _renderer(name)
    with pytest.raises(ValueError, match="finite"):
        render(np.array([[[0.1, np.nan, 0.3]]], np.float32))
    with pytest.raises(ValueError):
        render(np.zeros((1, 1, 3), np.float32), exposure=float("inf"))
    with pytest.raises(ValueError):
        render(np.zeros((1, 1, 3), np.float32), exposure=-1)


@pytest.mark.parametrize("strength", [-0.1, 1.1, float("nan")])
def test_protection_rejects_invalid_strength(strength):
    protect = _renderer("render_protected")
    with pytest.raises(ValueError):
        protect(np.zeros((1, 1, 3), np.float32), strength=strength)


def test_decode_dng_headroom_and_source_unchanged_if_private_fixture_supplied():
    """Opt in with GRMOD_TEST_DNG; synthetic tests never imply RAW decoding."""
    fixture = os.environ.get("GRMOD_TEST_DNG")
    if not fixture:
        pytest.skip("Set GRMOD_TEST_DNG to run read-only local RAW integration check")
    import hashlib
    import rawpy

    path = Path(fixture)
    before = hashlib.sha256(path.read_bytes()).hexdigest()
    decode = _renderer("decode_raw")
    scene, metadata = decode(path, half_size=True)
    assert scene.dtype == np.float32 and scene.ndim == 3 and scene.shape[-1] == 3
    assert np.isfinite(scene).all() and scene.min() >= 0
    assert metadata["source_path"] == str(path.resolve())
    assert metadata["decoder_settings"]["exp_shift"] == 0.25
    assert metadata["decoder_settings"]["gamma"] == [1, 1]
    assert metadata["scene_normalization_multiplier"] == 4.0
    assert metadata["wb_basis"] == "camera white balance recorded in the RAW"
    assert metadata["dimensions"] == {"width": scene.shape[1], "height": scene.shape[0]}
    settings = dict(half_size=True, output_color=rawpy.ColorSpace.sRGB,
                    output_bps=16, gamma=(1, 1), no_auto_bright=True,
                    use_camera_wb=True, exp_preserve_highlights=0.0,
                    bright=1.0, highlight_mode=rawpy.HighlightMode.Clip,
                    adjust_maximum_thr=0.0)
    with rawpy.imread(str(path)) as raw:
        unshifted = raw.postprocess(exp_shift=1.0, **settings).astype(np.float32) / 65535.0
    middle = (unshifted > 0.03) & (unshifted < 0.25)
    assert np.count_nonzero(middle) > 100
    ratio = np.median(scene[middle] / unshifted[middle])
    assert abs(float(ratio) - 1.0) < 0.01
    # For fixtures with real bright channels, reduction should retain differences
    # that the same LibRaw pipeline at exp_shift=1.0 clipped to display white.
    if metadata["headroom"]["pixels_with_channel_above_one"]:
        assert scene.max() > 1.0
        assert np.any(unshifted[scene > 1.01] >= 0.999)
    after = hashlib.sha256(path.read_bytes()).hexdigest()
    assert before == after
