"""Offline scene-linear RAW decoding and rendering experiments.

The decoder returns nonnegative float32 linear sRGB, including values above 1.
The renderers return display sRGB float32 in [0, 1]. This is a common offline
LibRaw rendering basis, not the camera JPEG engine or a change to the capture.

LibRaw's 16-bit output otherwise clips RGB channels at display white after WB
and colour conversion. ``exp_shift=0.25`` reduces exposure inside LibRaw before
that ceiling; multiplying the linear output by four restores the common scene
normalization. This scaling was measured with rawpy 0.27.1 / LibRaw 0.22.1 on a
local Ricoh DNG (see raw_notes.json), and an optional read-only integration test
checks the relationship against an unshifted decode on the supplied fixture.
It does not restore sensor-clipped data, negative output RGB or JPEG detail.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import numpy as np


_DECODE_EXPOSURE = 0.25
_SHOULDER_KNEE = 0.5
_LUMA = np.array([0.2126, 0.7152, 0.0722], dtype=np.float32)


def _number(value: float, name: str, low: float = 0.0, high: float = np.inf) -> float:
    value = float(value)
    if not np.isfinite(value) or not low <= value <= high:
        raise ValueError(f"{name} must be finite and between {low} and {high}")
    return value


def _scene(linear_rgb: np.ndarray, exposure: float) -> np.ndarray:
    """Allocate an exposed scene without ever modifying the supplied array."""
    exposure = _number(exposure, "exposure")
    scene = np.asarray(linear_rgb, dtype=np.float32)
    if scene.ndim < 1 or scene.shape[-1] != 3 or scene.size == 0:
        raise ValueError("linear_rgb must be a nonempty RGB array with last dimension 3")
    if not np.isfinite(scene).all():
        raise ValueError("linear_rgb must contain only finite values")
    # LibRaw has already clipped negatives after conversion to output RGB. Also
    # make that convention explicit for externally supplied scene-linear arrays.
    with np.errstate(over="ignore", invalid="ignore"):
        exposed = np.maximum(scene, 0.0) * np.float32(exposure)
    if not np.isfinite(exposed).all():
        raise ValueError("exposed linear_rgb must remain finite in float32")
    return exposed


def _srgb(linear: np.ndarray) -> np.ndarray:
    linear = np.clip(linear, 0.0, 1.0)
    encoded = np.where(linear <= 0.0031308, 12.92 * linear,
                       1.055 * np.power(linear, 1.0 / 2.4) - 0.055)
    return np.clip(encoded, 0.0, 1.0).astype(np.float32)


def decode_raw(path: str | Path, half_size: bool = False,
               wb_mode: str = "camera") -> tuple[np.ndarray, dict[str, Any]]:
    """Decode actual RAW data with two stops of output-container headroom.

    ``camera`` uses the recorded camera WB, ``daylight`` uses LibRaw's daylight
    multipliers and ``auto`` requests LibRaw's image-based automatic WB. The
    orientation recorded in the RAW is applied by LibRaw. No source is written.
    ``adjust_maximum_thr=0`` disables the scene-dependent maximum adjustment;
    normal sensor scaling and black subtraction remain enabled.

    Values have a theoretical output-container range of 0..4, whose usable
    extent depends on the source. They are not absolute radiance measurements.
    Missing camera WB raises an error rather than silently claiming camera WB.
    """
    import rawpy

    if wb_mode not in {"camera", "daylight", "auto"}:
        raise ValueError("wb_mode must be 'camera', 'daylight', or 'auto'")
    source = Path(path).expanduser().resolve(strict=True)
    settings = dict(
        demosaic_algorithm=rawpy.DemosaicAlgorithm.AHD,
        half_size=bool(half_size),
        four_color_rgb=False,
        fbdd_noise_reduction=rawpy.FBDDNoiseReductionMode.Off,
        noise_thr=None,
        median_filter_passes=0,
        use_camera_wb=wb_mode == "camera",
        use_auto_wb=wb_mode == "auto",
        user_wb=None,
        output_color=rawpy.ColorSpace.sRGB,
        output_bps=16,
        user_flip=None,
        no_auto_bright=True,
        no_auto_scale=False,
        adjust_maximum_thr=0.0,
        bright=1.0,
        highlight_mode=rawpy.HighlightMode.Clip,
        exp_shift=_DECODE_EXPOSURE,
        exp_preserve_highlights=0.0,
        gamma=(1, 1),
    )
    with rawpy.imread(str(source)) as raw:
        camera_wb = [float(value) for value in raw.camera_whitebalance]
        daylight_wb = [float(value) for value in raw.daylight_whitebalance]
        if wb_mode == "camera" and not all(value > 0 for value in camera_wb[:3]):
            raise ValueError("RAW has no usable recorded camera white balance")
        sensor = raw.raw_image_visible
        sensor_data = {
            "declared_white_level": int(raw.white_level),
            "black_levels": [int(value) for value in raw.black_level_per_channel],
            "maximum_visible_raw_sample": int(sensor.max()),
            "sensor_samples_at_or_above_declared_white": int(np.count_nonzero(sensor >= raw.white_level)),
            "raw_orientation_flip": int(raw.sizes.flip),
        }
        decoded = raw.postprocess(**settings)

    scene = decoded.astype(np.float32) * np.float32(1.0 / (65535.0 * _DECODE_EXPOSURE))
    any_over_one = np.any(scene > 1.0, axis=-1)
    any_at_ceiling = np.any(decoded == 65535, axis=-1)
    serial_settings = {
        key: (value.name if hasattr(value, "name") else list(value) if isinstance(value, tuple) else value)
        for key, value in settings.items()
    }
    metadata = {
        "source_path": str(source),
        "rendering_basis": "nonnegative scene-linear sRGB from actual RAW; values above 1 retained",
        "rawpy_version": rawpy.__version__,
        "libraw_version": ".".join(str(value) for value in rawpy.libraw_version),
        "decoder_settings": serial_settings,
        "scene_normalization_multiplier": 1.0 / _DECODE_EXPOSURE,
        "scene_quantization_step": 1.0 / (65535.0 * _DECODE_EXPOSURE),
        "wb_mode": wb_mode,
        "wb_basis": {
            "camera": "camera white balance recorded in the RAW",
            "daylight": "LibRaw daylight white balance",
            "auto": "LibRaw automatic white balance estimated from the RAW",
        }[wb_mode],
        "recorded_camera_wb_multipliers_rgbg": camera_wb,
        "daylight_wb_multipliers_rgbg": daylight_wb,
        "dimensions": {"width": int(scene.shape[1]), "height": int(scene.shape[0])},
        "orientation": "RAW orientation applied by LibRaw; do not apply EXIF rotation again",
        "sensor": sensor_data,
        "headroom": {
            "maximum_scene_channel": float(scene.max()),
            "pixels_with_channel_above_one": int(np.count_nonzero(any_over_one)),
            "fraction_pixels_with_channel_above_one": float(np.mean(any_over_one)),
            "pixels_at_decoder_ceiling": int(np.count_nonzero(any_at_ceiling)),
            "theoretical_output_container_ceiling": 1.0 / _DECODE_EXPOSURE,
        },
        "exposure_scale_validation": "See raw_notes.json and GRMOD_TEST_DNG integration test; ordinary channels retain the same normalization after restoring the 0.25 exposure scale",
        "recipe_wb_basis": "relative diagonal RGB gain in already white-balanced scene-linear sRGB; not sensor-space WB or a Kelvin calibration",
        "baseline_render": "clip exposed scene-linear RGB to [0,1], then standard sRGB transfer",
        "protected_render": "identity below peak 0.5; monotonic rational shoulder above, uniform RGB scale; strength blends with ordinary clipping before sRGB transfer",
        "limitations": [
            "Offline experiment, not a camera-verified JPEG engine or a new capture exposure.",
            "Sensor-saturated samples and detail already clipped in camera cannot be recovered.",
            "LibRaw's output conversion clips negative RGB; this is not a full floating-point wide-gamut RAW development pipeline.",
            "The 16-bit quarter-exposure output trades two bits of container precision for two stops of container headroom.",
            "Half-size development changes demosaicing and pixel scale; matched comparisons must use the same decode.",
        ],
    }
    return scene, metadata


def render_baseline(linear_rgb: np.ndarray, exposure: float = 1.0) -> np.ndarray:
    """Render the declared common RAW baseline with ordinary sRGB clipping."""
    return _srgb(_scene(linear_rgb, exposure))


def render_protected(linear_rgb: np.ndarray, exposure: float = 1.0,
                     strength: float = 0.7) -> np.ndarray:
    """Compress genuine decoded highlights without moving peaks below 0.5.

    For peak p above knee k=0.5, the protected peak is
    ``k + (1-k)*(p-k)/((1-k)+(p-k))``. Its derivative is positive,
    its first derivative joins the identity at k and it tends towards 1.
    All channels share the peak's scale, retaining linear RGB ratios at full
    strength. A linear-light blend with the clipped baseline makes strength=0
    exactly the baseline. A partially clipped baseline contribution can still
    affect highlight hue at intermediate strengths.
    """
    strength = _number(strength, "strength", high=1.0)
    scene = _scene(linear_rgb, exposure)
    if strength == 0:
        return _srgb(scene)
    peak = np.max(scene, axis=-1, keepdims=True)
    over = np.maximum(peak - _SHOULDER_KNEE, 0.0)
    shoulder = np.where(peak <= _SHOULDER_KNEE, peak,
                        _SHOULDER_KNEE + (1.0 - _SHOULDER_KNEE) * over / ((1.0 - _SHOULDER_KNEE) + over))
    scale = np.divide(shoulder, peak, out=np.ones_like(peak), where=peak > 0)
    protected = scene * scale
    blended = (1.0 - strength) * np.minimum(scene, 1.0) + strength * protected
    return _srgb(blended)


def _white_balanced_scene(linear_rgb: np.ndarray, exposure: float,
                          warmth: float, tint: float) -> np.ndarray:
    warmth = _number(warmth, "warmth", low=-1.0, high=1.0)
    tint = _number(tint, "tint", low=-1.0, high=1.0)
    scene = _scene(linear_rgb, exposure)
    gains = np.exp(np.array([warmth + tint / 2, -tint, -warmth + tint / 2], dtype=np.float32))
    gains /= np.dot(gains, _LUMA)
    return scene * gains


def render_white_balance(linear_rgb: np.ndarray, exposure: float = 1.0,
                         warmth: float = 0.06, tint: float = 0.0) -> np.ndarray:
    """Isolate relative linear RGB WB, followed by the baseline's hard clipping.

    Uses the same luminance-normalized log gains as render_recipe but adds no
    highlight shoulder, texture or other grading. The source is already camera
    white-balanced; these controls are neither Kelvin nor sensor-space WB.
    """
    return _srgb(_white_balanced_scene(linear_rgb, exposure, warmth, tint))


def render_recipe(linear_rgb: np.ndarray, exposure: float = 1.0,
                  warmth: float = 0.06, tint: float = 0.0) -> np.ndarray:
    """Apply a relative linear-light WB look and the default highlight shoulder.

    Positive warmth increases red versus blue; positive tint increases magenta
    versus green. These are dimensionless log-gain controls in [-1,1], not a
    Kelvin/green-magenta camera WB setting. The gains have unit Rec.709-weighted
    luminance on a neutral input, so a WB shift need not add a brightness shift.
    The source was already developed with the WB declared by ``decode_raw``.
    """
    return render_protected(_white_balanced_scene(linear_rgb, exposure, warmth, tint), strength=0.7)
