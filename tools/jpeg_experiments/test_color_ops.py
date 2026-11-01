"""Behaviour checks for display-sRGB colour experiments (no photo fixtures)."""

import colorsys

import numpy as np
import pytest

import color_ops as ops


OPERATIONS = [ops.colour_density, ops.blue_density, ops.highlight_gamut, ops.skin_tone_colour]


def _luma(rgb):
    """Independent display-domain brightness proxy for relative comparisons."""
    return np.asarray(rgb) @ np.array([0.2126, 0.7152, 0.0722])


@pytest.mark.parametrize("operation", OPERATIONS)
def test_zero_strength_is_exact_identity_and_does_not_mutate(operation):
    source = np.random.default_rng(12).random((9, 11, 3), dtype=np.float32)
    original = source.copy()
    result = operation(source, strength=0)
    np.testing.assert_array_equal(result, source)
    np.testing.assert_array_equal(source, original)
    assert result.dtype == np.float32
    assert not np.shares_memory(result, source)


@pytest.mark.parametrize("operation", OPERATIONS)
def test_colour_functions_are_finite_bounded_and_accept_pixel_lists(operation):
    source = np.random.default_rng(4).random((700, 3), dtype=np.float32)
    original = source.copy()
    result = operation(source, strength=1)
    assert result.shape == source.shape
    assert result.dtype == np.float32
    assert np.isfinite(result).all()
    assert 0 <= result.min() <= result.max() <= 1
    np.testing.assert_array_equal(source, original)


@pytest.mark.parametrize("operation", [ops.colour_density, ops.blue_density])
def test_selective_density_does_not_darken_or_tint_neutral_ramps(operation):
    source = np.repeat(np.linspace(0, 1, 513, dtype=np.float32)[:, None], 3, axis=1)
    np.testing.assert_allclose(operation(source, strength=1), source, atol=2e-6)


def test_colour_density_deepens_saturated_colour_and_spares_low_chroma_skin():
    # Green fabric and blue sky should gain density. Muted warm skin should barely move.
    source = np.array([[0.24, 0.65, 0.28], [0.25, 0.49, 0.80], [0.72, 0.58, 0.49]], np.float32)
    result = ops.colour_density(source, strength=0.8)
    brightness_change = _luma(source) - _luma(result)
    assert brightness_change[0] > 0.012
    assert brightness_change[1] > 0.008
    assert 0 <= brightness_change[2] < 0.006
    # Density is not broad desaturation: the green spread remains substantial.
    assert np.ptp(result[0]) > 0.90 * np.ptp(source[0])


def test_blue_density_leaves_warm_colour_and_neutral_untouched():
    source = np.array([[0.25, 0.49, 0.80], [0.76, 0.40, 0.20], [0.5, 0.5, 0.5]], np.float32)
    result = ops.blue_density(source, strength=0.8)
    assert _luma(source[0]) - _luma(result[0]) > 0.018
    np.testing.assert_allclose(result[1:], source[1:], atol=2e-6)
    # Independent density must not perform the existing teal channel mixer.
    before_hue = colorsys.rgb_to_hsv(*source[0])[0]
    after_hue = colorsys.rgb_to_hsv(*result[0])[0]
    assert abs(before_hue - after_hue) < 0.015


def test_density_masks_are_continuous_across_hue_and_neutral_boundaries():
    hues = np.linspace(0, 1, 4097, dtype=np.float32)
    source = np.asarray([colorsys.hsv_to_rgb(float(h), 0.45, 0.7) for h in hues], np.float32)
    for operation in [ops.colour_density, ops.blue_density]:
        change = operation(source, strength=1) - source
        assert np.max(np.abs(np.diff(change, axis=0))) < 0.0015
        np.testing.assert_allclose(change[0], change[-1], atol=2e-6)
    neutral_approach = np.tile(np.array([0.5, 0.5, 0.5], np.float32), (1025, 1))
    neutral_approach[:, 2] += np.linspace(-0.01, 0.01, 1025)
    result = ops.blue_density(neutral_approach, strength=1)
    assert np.max(np.abs(np.diff(result - neutral_approach, axis=0))) < 1e-5


def test_highlight_shoulder_is_neutral_monotone_and_preserves_midtone_exposure():
    source = np.repeat(np.linspace(0, 1, 4097, dtype=np.float32)[:, None], 3, axis=1)
    result = ops.highlight_gamut(source, strength=1)
    np.testing.assert_allclose(result[:, 0], result[:, 1], atol=2e-6)
    np.testing.assert_allclose(result[:, 1], result[:, 2], atol=2e-6)
    assert np.all(np.diff(result[:, 0]) > 0)
    assert 0.90 < result[-1, 0] < 0.99
    np.testing.assert_allclose(result[2048], source[2048], atol=2e-6)
    # No clipped plateau or visible jump at the shoulder knee.
    assert np.max(np.diff(result[:, 0])) < 0.0004


def test_highlight_gamut_compresses_saturated_highlights_smoothly():
    source = np.tile(np.array([0.28, 0.58, 0.9], np.float32), (2049, 1))
    source[:, 2] = np.linspace(0.9, 1, 2049)
    result = ops.highlight_gamut(source, strength=0.8)
    assert np.isfinite(result).all()
    assert np.max(np.abs(np.diff(result, axis=0))) < 0.0003
    assert np.max(result) < 1
    assert np.ptp(result[-1]) < np.ptp(source[-1])


def test_brightness_colour_is_skin_protected_and_strengthens_mid_colour():
    source = np.array([[0.72, 0.58, 0.49], [0.28, 0.65, 0.32], [0.10, 0.20, 0.12]], np.float32)
    result = ops.skin_tone_colour(source, strength=1)
    assert np.linalg.norm(result[0] - source[0]) < 0.012
    assert np.linalg.norm(result[1] - source[1]) > 0.012
    assert not np.allclose(result[1] - source[1], result[2] - source[2])


def test_graded_neutral_tint_changes_with_brightness_but_preserves_endpoints():
    source = np.repeat(np.array([0, 0.20, 0.85, 1], np.float32)[:, None], 3, axis=1)
    result = ops.skin_tone_colour(source, strength=1)
    np.testing.assert_allclose(result[[0, 3]], source[[0, 3]], atol=2e-6)
    assert result[1, 2] > result[1, 0]  # subtle cool shadow bias
    assert result[2, 0] > result[2, 2]  # subtle warm highlight bias
    assert np.ptp(result[1]) < 0.035
    assert np.ptp(result[2]) < 0.035


def test_identity_lut_interpolates_arbitrary_pixels_and_corners():
    axis = np.linspace(0, 1, 17, dtype=np.float32)
    identity = np.stack(np.meshgrid(axis, axis, axis, indexing="ij"), axis=-1)
    source = np.random.default_rng(22).random((27, 19, 3), dtype=np.float32)
    source[0, :4] = [[0, 0, 0], [1, 1, 1], [0, 1, 0], [1, 0, 1]]
    original = source.copy()
    result = ops.apply_lut(source, identity)
    np.testing.assert_allclose(result, source, atol=2e-7)
    np.testing.assert_array_equal(source, original)


def test_lut_uses_all_eight_corners_with_red_green_blue_axis_order():
    # Only RGB corner 111 is nonzero: trilinear interpolation is r*g*b.
    lut = np.zeros((2, 2, 2, 3), dtype=np.float32)
    lut[1, 1, 1] = [1, 0.5, 0.25]
    source = np.array([[0.25, 0.50, 0.75]], np.float32)
    np.testing.assert_allclose(ops.apply_lut(source, lut), [[0.09375, 0.046875, 0.0234375]], atol=1e-7)
    lut[..., 0] = np.array([0, 1], np.float32)[:, None, None]
    np.testing.assert_allclose(ops.apply_lut(source, lut)[..., 0], [0.25], atol=1e-7)


def test_built_17_cube_samples_direct_target_and_is_useful():
    lut = ops.build_lut()
    assert lut.shape == (17, 17, 17, 3)
    assert lut.dtype == np.float32
    axis = np.linspace(0, 1, 17, dtype=np.float32)
    grid = np.stack(np.meshgrid(axis, axis, axis, indexing="ij"), axis=-1)
    np.testing.assert_allclose(lut, ops.lut_target(grid), atol=1e-7)
    source = np.random.default_rng(88).uniform(0.08, 0.92, (1000, 3)).astype(np.float32)
    direct = ops.lut_target(source)
    interpolated = ops.apply_lut(source, lut)
    assert np.mean(np.abs(direct - source)) > 0.004
    assert np.mean(np.abs(interpolated - direct)) < 0.0025
    assert np.quantile(np.abs(interpolated - direct), 0.99) < 0.012


def test_direct_target_has_no_saturated_blue_gamut_branch_jump():
    # OkLab's blue cusp can have a non-convex gamut intersection; a conditional
    # chroma bisection may jump between branches as red crosses the boundary.
    source = np.tile(np.array([0.0, 0.145, 0.90], np.float32), (2049, 1))
    source[:, 0] = np.linspace(0, 0.065, 2049)
    direct = ops.lut_target(source)
    assert np.max(np.abs(np.diff(direct, axis=0))) < 0.003


def test_chunk_boundaries_do_not_change_colour_or_lut_results():
    # Exceed a processing chunk with a repeated ramp to exercise more than one batch.
    source = np.tile(np.linspace(0.05, 0.95, 513, dtype=np.float32)[:, None], (300, 3))
    for operation in [ops.colour_density, ops.blue_density, ops.highlight_gamut, ops.skin_tone_colour]:
        expected = operation(source[:513])
        result = operation(source)
        np.testing.assert_array_equal(result[-513:], expected)
    lut = ops.build_lut()
    np.testing.assert_array_equal(ops.apply_lut(source, lut)[-513:], ops.apply_lut(source[:513], lut))


def test_invalid_shapes_strengths_and_luts_are_rejected():
    with pytest.raises(ValueError):
        ops.colour_density(np.zeros((5, 4), np.float32))
    for strength in [-0.1, 1.1, float("nan")]:
        with pytest.raises(ValueError):
            ops.blue_density(np.zeros((1, 3), np.float32), strength)
    with pytest.raises(ValueError):
        ops.build_lut(1)
    with pytest.raises(ValueError):
        ops.apply_lut(np.zeros((1, 3), np.float32), np.zeros((2, 3, 2, 3), np.float32))


def test_nonfinite_and_out_of_domain_input_is_sanitized_without_mutation():
    source = np.array([[np.nan, np.inf, -np.inf], [-0.1, 0.5, 1.2]], np.float32)
    result = ops.colour_density(source, strength=0)
    np.testing.assert_array_equal(result, [[0, 1, 0], [0, 0.5, 1]])
    assert np.isnan(source[0, 0])


def test_tiny_positive_strength_is_stable_in_float32():
    source = np.array([[0.3, 0.6, 0.9], [1, 1, 1]], np.float32)
    with np.errstate(all="raise"):
        for operation in OPERATIONS:
            np.testing.assert_array_equal(operation(source, strength=1e-300), source)
