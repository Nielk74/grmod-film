"""Behavioral checks for the offline JPEG texture experiments."""

import importlib.util
from pathlib import Path

import numpy as np
import pytest


MODULE_PATH = Path(__file__).with_name("texture_ops.py")


def _module():
    spec = importlib.util.spec_from_file_location("jpeg_texture_ops", MODULE_PATH)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.fixture
def ops():
    return _module()


@pytest.mark.parametrize("name", ["film_texture", "adaptive_grain", "monochrome"])
def test_operations_do_not_mutate_input_and_return_bounded_float32(ops, name):
    rgb = np.random.default_rng(9).random((80, 96, 3), dtype=np.float32)
    saved = rgb.copy()
    result = getattr(ops, name)(rgb)
    np.testing.assert_array_equal(rgb, saved)
    assert not np.shares_memory(rgb, result)
    assert result.shape == rgb.shape
    assert result.dtype == np.float32
    assert np.isfinite(result).all()
    assert result.min() >= 0 and result.max() <= 1


@pytest.mark.parametrize("value", [0.0, 0.18, 0.5, 1.0])
def test_film_texture_preserves_constant_patches(ops, value):
    rgb = np.full((56, 63, 3), value, dtype=np.float32)
    np.testing.assert_allclose(ops.film_texture(rgb, strength=1), rgb, atol=2e-7)


@pytest.mark.parametrize("name", ["film_texture", "adaptive_grain"])
def test_zero_strength_is_exact_identity(ops, name):
    rgb = np.random.default_rng(3).random((48, 64, 3), dtype=np.float32)
    np.testing.assert_array_equal(getattr(ops, name)(rgb, strength=0), rgb)


@pytest.mark.parametrize("name", ["film_texture", "adaptive_grain"])
def test_neutral_images_remain_achromatic(ops, name):
    ramp = np.broadcast_to(np.linspace(0, 1, 192, dtype=np.float32), (80, 192))
    result = getattr(ops, name)(np.repeat(ramp[..., None], 3, axis=2))
    np.testing.assert_array_equal(result[..., 0], result[..., 1])
    np.testing.assert_array_equal(result[..., 0], result[..., 2])


def test_film_texture_softens_pixel_scale_detail_without_erasing_middle_scale(ops):
    x = np.arange(512, dtype=np.float32)
    fine = 0.08 * np.cos(np.pi * x)
    middle = 0.08 * np.sin(2 * np.pi * x / 24)
    rgb = np.repeat(np.broadcast_to(0.5 + fine + middle, (48, 512))[..., None], 3, axis=2)
    result = ops.film_texture(rgb, strength=1)[0, 24:-24, 0] - 0.5
    fine_gain = np.dot(result, fine[24:-24]) / np.dot(fine[24:-24], fine[24:-24])
    middle_gain = np.dot(result, middle[24:-24]) / np.dot(middle[24:-24], middle[24:-24])
    assert 0.6 < fine_gain < 0.95
    assert 0.95 < middle_gain < 1.15


def test_texture_avoids_large_edge_halos_and_preserves_colour_differences(ops):
    rgb = np.empty((64, 160, 3), dtype=np.float32)
    rgb[:, :80] = [0.15, 0.25, 0.35]
    rgb[:, 80:] = [0.65, 0.75, 0.85]
    result = ops.film_texture(rgb, strength=1)
    assert np.max(np.abs(result - rgb)) < 0.025
    np.testing.assert_allclose(result[..., 0] - result[..., 1], -0.1, atol=1e-6)
    np.testing.assert_allclose(result[..., 1] - result[..., 2], -0.1, atol=1e-6)


def test_grain_is_seeded_multiscale_and_nearly_zero_mean(ops):
    rgb = np.full((256, 320, 3), 0.45, dtype=np.float32)
    first = ops.adaptive_grain(rgb, seed=7)
    np.testing.assert_array_equal(first, ops.adaptive_grain(rgb, seed=7))
    assert not np.array_equal(first, ops.adaptive_grain(rgb, seed=8))
    delta = first[..., 0] - rgb[..., 0]
    assert 0.002 < delta.std() < 0.02
    assert abs(delta.mean()) < 1e-5
    assert np.corrcoef(delta[:, :-1].ravel(), delta[:, 1:].ravel())[0, 1] > 0.12


def test_grain_amount_falls_as_iso_increases(ops):
    rgb = np.full((160, 192, 3), 0.45, dtype=np.float32)
    amounts = [np.std(ops.adaptive_grain(rgb, iso=iso) - rgb) for iso in [100, 800, 6400]]
    assert amounts[2] < amounts[1] < amounts[0]
    assert amounts[2] < 0.6 * amounts[0]


def test_grain_respects_existing_noise_and_detail(ops):
    clean = np.full((192, 224, 3), 0.45, dtype=np.float32)
    noise = np.random.default_rng(11).normal(0, 0.05, clean.shape[:2]).astype(np.float32)
    noisy = clean + noise[..., None]
    added_clean = ops.adaptive_grain(clean) - clean
    added_noisy = ops.adaptive_grain(noisy) - noisy
    assert np.std(added_noisy) < 0.7 * np.std(added_clean)


def test_grain_protects_clipped_endpoints_and_is_tone_modulated(ops):
    patches = [np.full((128, 128, 3), value, dtype=np.float32) for value in [0, 0.03, 0.45, 0.98, 1]]
    amounts = [np.std(ops.adaptive_grain(rgb) - rgb) for rgb in patches]
    assert amounts[0] == amounts[4] == 0
    assert amounts[2] > 2 * amounts[1]
    assert amounts[2] > 2 * amounts[3]


def test_grain_scale_tracks_full_frame_width(ops):
    rgb = np.full((192, 256, 3), 0.45, dtype=np.float32)
    native = ops.adaptive_grain(rgb, frame_width=6000)[..., 0] - 0.45
    reduced = ops.adaptive_grain(rgb, frame_width=2400)[..., 0] - 0.45
    corr = lambda x: np.corrcoef(x[:, :-1].ravel(), x[:, 1:].ravel())[0, 1]
    assert corr(reduced) < corr(native)
    assert np.std(reduced) < np.std(native)


def test_monochrome_has_equal_channels_and_reproducible_grain(ops):
    rgb = np.random.default_rng(6).random((64, 96, 3), dtype=np.float32)
    result = ops.monochrome(rgb, seed=17)
    np.testing.assert_array_equal(result, ops.monochrome(rgb, seed=17))
    np.testing.assert_array_equal(result[..., 0], result[..., 1])
    np.testing.assert_array_equal(result[..., 0], result[..., 2])


def test_monochrome_tone_is_monotonic_on_neutral_ramp_without_grain(ops):
    ramp = np.broadcast_to(np.linspace(0, 1, 1024, dtype=np.float32), (16, 1024))
    rgb = np.repeat(ramp[..., None], 3, axis=2)
    result = ops.monochrome(rgb, strength=1, grain_strength=0)
    assert np.all(np.diff(result[8, :, 0]) > 0)
    assert result[8, 0, 0] == 0 and result[8, -1, 0] == 1
    assert result[8, 200, 0] < rgb[8, 200, 0]
    assert result[8, 800, 0] > rgb[8, 800, 0]


def test_monochrome_zero_strength_is_plain_luma_and_filter_response_is_deliberate(ops):
    rgb = np.array([[[1, 0, 0], [0, 1, 0], [0, 0, 1]]], dtype=np.float32)
    plain = ops.monochrome(rgb, strength=0)
    np.testing.assert_allclose(plain[0, :, 0], [0.299, 0.587, 0.114], atol=1e-6)
    filtered = ops.monochrome(rgb, strength=1, grain_strength=0)[0, :, 0]
    assert filtered[2] < plain[0, 2, 0]
    assert filtered[1] > plain[0, 1, 0]


@pytest.mark.parametrize("name", ["film_texture", "adaptive_grain", "monochrome"])
def test_invalid_images_are_rejected_instead_of_propagating_nan(ops, name):
    function = getattr(ops, name)
    with pytest.raises(ValueError):
        function(np.ones((8, 8), dtype=np.float32))
    with pytest.raises(ValueError):
        function(np.full((8, 8, 3), np.nan, dtype=np.float32))
    with pytest.raises(ValueError):
        function(np.full((8, 8, 3), 1.1, dtype=np.float32))
    with pytest.raises(ValueError):
        function(np.zeros((8, 8, 3), dtype=np.float32), strength=-0.1)
