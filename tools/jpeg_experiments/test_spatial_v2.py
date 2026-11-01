"""Behavioral checks for whole-frame spatial finishing experiments."""

import importlib.util
from pathlib import Path

import numpy as np
import pytest


MODULE_PATH = Path(__file__).with_name("spatial_v2.py")
NAMES = ["local_contrast", "bloom", "vignette", "local_range"]


@pytest.fixture(scope="module")
def ops():
    spec = importlib.util.spec_from_file_location("jpeg_spatial_v2", MODULE_PATH)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _rgb(grey):
    return np.repeat(np.asarray(grey, dtype=np.float32)[..., None], 3, axis=2)


def _linear(rgb):
    return np.where(rgb <= 0.04045, rgb / 12.92, ((rgb + 0.055) / 1.055) ** 2.4)


def _display(linear):
    linear = np.asarray(linear, dtype=np.float32)
    return np.where(linear <= 0.0031308, linear * 12.92,
                    1.055 * linear ** (1 / 2.4) - 0.055)


@pytest.mark.parametrize("name", NAMES)
def test_float32_bounded_output_without_mutating_or_aliasing_input(ops, name):
    rgb = np.random.default_rng(8).random((67, 89, 3), dtype=np.float32)
    saved = rgb.copy()
    rgb.flags.writeable = False
    result = getattr(ops, name)(rgb, strength=3)
    np.testing.assert_array_equal(rgb, saved)
    assert result.shape == rgb.shape and result.dtype == np.float32
    assert not np.shares_memory(rgb, result)
    assert np.isfinite(result).all() and result.min() >= 0 and result.max() <= 1


@pytest.mark.parametrize("name", NAMES)
def test_zero_strength_is_exact_independent_identity(ops, name):
    rgb = np.random.default_rng(4).random((31, 47, 3), dtype=np.float32)
    result = getattr(ops, name)(rgb, strength=0)
    np.testing.assert_array_equal(result, rgb)
    assert not np.shares_memory(rgb, result)


@pytest.mark.parametrize("colour", [[0, 0, 0], [.3, .3, .3], [.7, .4, .2], [1, 1, 1]])
def test_local_contrast_does_not_change_uniform_colour(ops, colour):
    rgb = np.broadcast_to(np.array(colour, dtype=np.float32), (57, 83, 3)).copy()
    np.testing.assert_allclose(ops.local_contrast(rgb, strength=3), rgb, atol=2e-7)


def test_local_contrast_has_visible_broad_scale_effect_and_monotonic_strength(ops):
    x = np.arange(720, dtype=np.float32)
    grey = .47 + .12 * np.sin(2 * np.pi * x / 180)
    rgb = _rgb(np.broadcast_to(grey, (80, len(x))))
    changes = [np.mean(np.abs(ops.local_contrast(rgb, strength=s) - rgb))
               for s in [.5, 1, 2, 3]]
    assert changes[1] > .02
    assert np.all(np.diff(changes) > .008)
    assert changes[-1] > 2 * changes[1]


def test_local_contrast_enhances_broad_structure_without_amplifying_pixel_texture(ops):
    x = np.arange(720, dtype=np.float32)
    fine = .04 * np.cos(np.pi * x)
    broad = .25 * np.sin(2 * np.pi * x / 180)
    log_luma = -2.5 + fine + broad
    rgb = _rgb(np.broadcast_to(_display(2 ** log_luma), (80, 720)))
    result = np.log2(_linear(ops.local_contrast(rgb, strength=1))[40, :, 0])
    delta = result[80:-80] - log_luma[80:-80]
    fine_delta_gain = np.dot(delta, fine[80:-80]) / np.dot(fine[80:-80], fine[80:-80])
    broad_delta_gain = np.dot(delta, broad[80:-80]) / np.dot(broad[80:-80], broad[80:-80])
    assert abs(fine_delta_gain) < .025
    assert broad_delta_gain > .35


def test_local_contrast_keeps_linear_rgb_ratios_until_gamut_boundary(ops):
    x = np.linspace(0, 6 * np.pi, 300, dtype=np.float32)
    light = .1 + .035 * np.sin(x)
    rgb = _display(np.broadcast_to(light[None, :, None] * [1, .6, .35], (40, 300, 3)))
    result = _linear(ops.local_contrast(rgb, strength=1, radius=30))
    np.testing.assert_allclose(result[..., 1] / result[..., 0], .6, atol=2e-6)
    np.testing.assert_allclose(result[..., 2] / result[..., 0], .35, atol=2e-6)


def test_spatial_radius_scales_with_whole_frame_long_side(ops):
    x = np.arange(600, dtype=np.float32)
    grey = .5 + .08 * np.sin(2 * np.pi * x / 100)
    rgb = _rgb(np.broadcast_to(grey, (80, len(x))))
    native = ops.local_contrast(rgb, radius=50, frame_width=6000)
    preview = ops.local_contrast(rgb[:, ::2], radius=50, frame_width=3000)
    np.testing.assert_allclose(preview[:, 12:-12], native[:, 24:-24:2], atol=.004)


def test_bloom_spreads_only_bright_content_and_retains_halo_colour(ops):
    dark = np.full((128, 192, 3), .3, dtype=np.float32)
    np.testing.assert_allclose(ops.bloom(dark, strength=3), dark, atol=2e-7)
    rgb = np.zeros((257, 257, 3), dtype=np.float32)
    rgb[128, 128] = _display(np.array([1, .7, .35], dtype=np.float32))
    result = _linear(ops.bloom(rgb, strength=1, radius=20))
    assert result[128, 145, 0] > .0001
    np.testing.assert_allclose(result[128, 145, 1:] / result[128, 145, 0], [.7, .35], atol=2e-5)
    assert result[128, 128, 0] >= .99999
    assert result[0, 0].max() < 1e-7


def test_bloom_impulse_radius_matches_declared_sigma_and_scales(ops):
    rgb = np.zeros((241, 241, 3), dtype=np.float32)
    rgb[120, 120] = 1
    for frame_width, expected_sigma in [(6000, 20), (3000, 10)]:
        result = _linear(ops.bloom(rgb, radius=20, frame_width=frame_width))[..., 0]
        result[120, 120] = 0
        y, x = np.mgrid[:241, :241]
        variance = np.sum(result * (x - 120) ** 2) / np.sum(result)
        assert abs(np.sqrt(variance) - expected_sigma) < 1.2


def test_bloom_default_is_visible_and_strength_sweep_is_monotonic(ops):
    rgb = np.full((120, 240, 3), .18, dtype=np.float32)
    rgb[:, 70:170] = .92
    changes = [np.mean(ops.bloom(rgb, strength=s, radius=50) - rgb)
               for s in [.5, 1, 2, 3]]
    assert changes[1] > .03
    assert np.all(np.diff(changes) > .005)


def test_vignette_one_strength_is_one_corner_ev_and_center_is_preserved(ops):
    rgb = np.full((101, 151, 3), .7, dtype=np.float32)
    result = ops.vignette(rgb, strength=1)
    np.testing.assert_allclose(result[50, 75], rgb[50, 75], atol=1e-7)
    np.testing.assert_allclose(_linear(result[0, 0]) / _linear(rgb[0, 0]), .5, atol=1e-6)
    assert .5 < _linear(result[50, 0, 0]) / _linear(rgb[50, 0, 0]) < 1
    corner_values = [ops.vignette(rgb, strength=s)[0, 0, 0] for s in [.5, 1, 2, 3]]
    assert np.all(np.diff(corner_values) < 0)


def test_vignette_rotates_with_frame_and_preserves_neutrals(ops):
    rgb = np.full((62, 91, 3), .55, dtype=np.float32)
    result = ops.vignette(rgb)
    np.testing.assert_array_equal(result[..., 0], result[..., 1])
    np.testing.assert_array_equal(result[..., 0], result[..., 2])
    np.testing.assert_allclose(ops.vignette(rgb.transpose(1, 0, 2)), result.transpose(1, 0, 2))


def test_local_range_compresses_broad_illumination_with_monotonic_strength(ops):
    ev = np.broadcast_to(np.linspace(-5, -0.6, 600, dtype=np.float32), (80, 600))
    rgb = _rgb(_display(2 ** ev))
    spans = []
    for strength in [0, .5, 1, 2, 3]:
        result = _linear(ops.local_range(rgb, strength=strength, radius=80))[..., 0]
        spans.append(np.log2(result[40, 550]) - np.log2(result[40, 50]))
    assert np.all(np.diff(spans) < -.15)
    assert spans[2] < .8 * spans[0]
    assert spans[-1] < .55 * spans[0]


def test_local_range_retains_fine_texture_and_avoids_edge_reversal(ops):
    x = np.arange(600, dtype=np.float32)
    fine = .055 * np.cos(2 * np.pi * x / 6)
    illumination = np.where(x < 300, -4, -1.3)
    rgb = _rgb(np.broadcast_to(_display(2 ** (illumination + fine)), (80, 600)))
    result = np.log2(_linear(ops.local_range(rgb, strength=1, radius=50))[40, :, 0])
    texture = result[60:240] - result[60:240].mean()
    gain = np.dot(texture, fine[60:240]) / np.dot(fine[60:240], fine[60:240])
    assert .85 < gain < 1.1
    assert result[295:300].max() < result[300:305].min()


@pytest.mark.parametrize("name", NAMES)
@pytest.mark.parametrize("strength", [-.1, 3.1, np.nan, np.inf])
def test_invalid_strength_is_rejected(ops, name, strength):
    with pytest.raises(ValueError):
        getattr(ops, name)(np.zeros((8, 8, 3), dtype=np.float32), strength=strength)


@pytest.mark.parametrize("name", NAMES)
def test_invalid_image_is_rejected(ops, name):
    for image in [np.zeros((8, 8)), np.zeros((0, 8, 3)),
                  np.full((8, 8, 3), np.nan), np.full((8, 8, 3), -0.1),
                  np.full((8, 8, 3), 1.1)]:
        with pytest.raises(ValueError):
            getattr(ops, name)(image)


@pytest.mark.parametrize("name", ["local_contrast", "bloom", "local_range"])
def test_invalid_spatial_scale_is_rejected_even_at_zero_strength(ops, name):
    image = np.zeros((8, 8, 3), dtype=np.float32)
    for invalid in [0, -1, np.nan, np.inf]:
        with pytest.raises(ValueError):
            getattr(ops, name)(image, strength=0, radius=invalid)
        with pytest.raises(ValueError):
            getattr(ops, name)(image, strength=0, frame_width=invalid)
