"""Visible whole-frame spatial finishing, for offline film-look comparisons.

All four operations accept nonempty H x W x 3 display-sRGB arrays in [0, 1]
and return independent, finite float32 arrays. They never modify the input.
Strength is 0..3: zero is exact identity, 1 is a useful visible treatment,
and 2..3 deliberately exposes an exaggerated version for comparison.

Spatial ``radius`` means Gaussian sigma in pixels on a 6000-pixel-long-side
frame, before EXIF rotation. Pass ``frame_width=max(rgb.shape[:2])`` when
processing a resized *whole frame*. A crop taken from a 6000px source still
uses 6000. The actual sigma is radius * frame_width / 6000. Broad Gaussian
fields use area reduction and bilinear reconstruction for sigmas >=16px;
this is a fast smooth approximation, not a camera pyramid implementation.

The existing native clarity table (core/src/fw/clarity.ts) has eleven bands
at approximately 2**i-pixel scales. Reweighting its middle/coarse bands may
offer a route to broad local contrast. The log-domain, highlight-threshold,
radial exposure, and guided compression operations here require additional
software processing: they are not encoded by eleven constant band gains.
No camera noise-reduction, HDF, or measured optical equivalence is claimed.
Native Image Control Shading already offers a creative falloff approximation;
its radial profile/EV per step are uncalibrated here. Native HDR Tone and
Shadow Correction may approximate local range; no match has been measured.
"""

from __future__ import annotations

import math

import numpy as np
from scipy.ndimage import gaussian_filter, zoom


def _prepare(rgb: np.ndarray, strength: float) -> tuple[np.ndarray, float]:
    image = np.asarray(rgb, dtype=np.float32)
    if image.ndim != 3 or image.shape[2] != 3 or not all(image.shape[:2]):
        raise ValueError("rgb must be a nonempty H x W x 3 array")
    if not np.isfinite(image).all() or image.min() < 0 or image.max() > 1:
        raise ValueError("rgb must contain finite display-sRGB values in [0, 1]")
    amount = float(strength)
    if not math.isfinite(amount) or not 0 <= amount <= 3:
        raise ValueError("strength must be finite and in [0, 3]")
    return image, amount


def _sigma(radius: float, frame_width: float) -> float:
    radius, frame_width = float(radius), float(frame_width)
    if not math.isfinite(radius) or radius <= 0:
        raise ValueError("radius must be finite and positive")
    if not math.isfinite(frame_width) or frame_width <= 0:
        raise ValueError("frame_width must be finite and positive")
    sigma = radius * (frame_width / 6000)
    if not math.isfinite(sigma) or sigma <= 0:
        raise ValueError("scaled radius must be finite and positive")
    return sigma


def _linear(rgb: np.ndarray) -> np.ndarray:
    return np.where(rgb <= .04045, rgb / 12.92,
                    ((rgb + .055) / 1.055) ** 2.4).astype(np.float32, copy=False)


def _display(linear: np.ndarray) -> np.ndarray:
    # One common scale for an out-of-gamut pixel retains its RGB ratios.
    # This only bounds the endpoint; it is not a small creative luma clamp.
    peak = np.maximum(np.max(linear, axis=2), 1)
    bounded = np.maximum(linear, 0) / peak[..., None]
    result = np.where(bounded <= .0031308, bounded * 12.92,
                      1.055 * bounded ** (1 / 2.4) - .055)
    return np.clip(result, 0, 1).astype(np.float32, copy=False)


def _luma(linear: np.ndarray) -> np.ndarray:
    return (.2126 * linear[..., 0] + .7152 * linear[..., 1]
            + .0722 * linear[..., 2])


def _log_luma(linear: np.ndarray) -> np.ndarray:
    # A 12-stop floor makes black neighbourhoods finite without adding light
    # to black source pixels when the exposure map is applied.
    return np.log2(np.maximum(_luma(linear), 2 ** -12))


def _reduce_area(field: np.ndarray, step: int) -> np.ndarray:
    """Average source blocks without padding a native 24MP-sized array."""
    h, w = field.shape
    rows = np.arange(0, h, step)
    cols = np.arange(0, w, step)
    reduced = np.add.reduceat(field, rows, axis=0)
    reduced = np.add.reduceat(reduced, cols, axis=1)
    row_counts = np.minimum(step, h - rows).astype(np.float32)
    col_counts = np.minimum(step, w - cols).astype(np.float32)
    reduced /= row_counts[:, None] * col_counts[None, :]
    return reduced


def _blur(field: np.ndarray, sigma: float) -> np.ndarray:
    # Keeping the reduced sigma at about 8px makes a 50..100px native field
    # practical. Small kernels remain exact; a block prefilter avoids aliasing
    # and, in particular, conserves the energy of tiny bright bloom sources.
    step = max(1, min(int(sigma // 8), max(field.shape)))
    if step == 1:
        return gaussian_filter(field, sigma=sigma, mode="reflect")
    reduced = _reduce_area(field, step)
    reduced = gaussian_filter(reduced, sigma=sigma / step, mode="reflect")
    return zoom(reduced, (field.shape[0] / reduced.shape[0],
                          field.shape[1] / reduced.shape[1]),
                order=1, prefilter=False, grid_mode=True, mode="nearest")


def _exposure(linear: np.ndarray, ev: np.ndarray) -> np.ndarray:
    return _display(linear * np.exp2(ev)[..., None])


def local_contrast(
    rgb: np.ndarray,
    strength: float = 1.0,
    radius: float = 50.0,
    frame_width: float = 6000,
) -> np.ndarray:
    """Enhance broad local structure with a log-luma band exposure map.

    The default 50px Gaussian sigma belongs to the 20..100px creative scale,
    rather than subpixel texture. The band between .4*radius and radius is
    enhanced: 20..50px at defaults. Strength 1 adds 100% of that log-luma
    residual; 3 adds 300%. Finer texture is retained without extra sharpening.
    A smooth 1.5EV residual shoulder limits only very large discontinuities.
    Linear RGB ratios are preserved unless the output reaches the gamut
    boundary. Uniform colours remain unchanged.
    """
    image, amount = _prepare(rgb, strength)
    sigma = _sigma(radius, frame_width)
    if amount == 0:
        return image.copy()
    linear = _linear(image)
    log_luma = _log_luma(linear)
    residual = _blur(log_luma, .4 * sigma) - _blur(log_luma, sigma)
    ev = np.float32(amount * 1.5) * np.tanh(residual / 1.5)
    return _exposure(linear, ev)


def bloom(
    rgb: np.ndarray,
    strength: float = 1.0,
    radius: float = 60.0,
    frame_width: float = 6000,
) -> np.ndarray:
    """Add broad, coloured highlight light without blurring the source.

    Above linear luminance .32 (about .60 display-sRGB), the emitted fraction
    rises smoothly to 1 at white. Only that bright RGB contribution is blurred
    with the declared sigma, then added at gain .85*strength in linear light.
    Shadow detail stays sharp underneath the glow. At strength 2..3 bright
    areas intentionally generate a conspicuous veil. The bloom colour follows
    the source highlight; this is not a measured lens or optical HDF model.
    """
    image, amount = _prepare(rgb, strength)
    sigma = _sigma(radius, frame_width)
    if amount == 0:
        return image.copy()
    linear = _linear(image)
    weight = np.clip((_luma(linear) - .32) / .68, 0, 1)
    weight *= weight * (3 - 2 * weight)
    for channel in range(3):
        # Use the unchanged source channel for emission. Other channels may
        # already contain bloom, but never feed back into the source luma.
        emitted = linear[..., channel] * weight
        linear[..., channel] += np.float32(.85 * amount) * _blur(emitted, sigma)
    return _display(linear)


def vignette(rgb: np.ndarray, strength: float = 1.0) -> np.ndarray:
    """Apply a broad radial exposure falloff, one corner stop per strength.

    The frame centre has zero falloff. Coordinates span -1..1 on each axis;
    EV loss is strength * ((x*x + y*y)/2)**1.4. Thus all four corners lose
    exactly 1EV at strength 1, and the side midpoints lose about .38EV.
    Attenuation is in linear light, so the stated stops are photographic EV.
    """
    image, amount = _prepare(rgb, strength)
    if amount == 0:
        return image.copy()
    h, w = image.shape[:2]
    x = np.linspace(-1, 1, w, dtype=np.float32) if w > 1 else np.zeros(1, dtype=np.float32)
    y = np.linspace(-1, 1, h, dtype=np.float32) if h > 1 else np.zeros(1, dtype=np.float32)
    radius_sq = (y[:, None] ** 2 + x[None, :] ** 2) * .5
    ev = np.float32(-amount) * radius_sq ** 1.4
    return _exposure(_linear(image), ev)


def local_range(
    rgb: np.ndarray,
    strength: float = 1.0,
    radius: float = 80.0,
    frame_width: float = 6000,
) -> np.ndarray:
    """Compress a coarse, edge-aware log-luma base while retaining detail.

    Gaussian guided-filter coefficients (regularization .25EV squared)
    separate the wide illumination/base field from the existing fine detail.
    That base is drawn toward .18 linear middle grey by 1-exp(-.36*strength):
    about 30% at 1 and 66% at 3. The residual detail is not multiplied by a
    softening gain. A broad 3EV shoulder bounds extreme exposure corrections.
    This changes the rendering of available JPEG tones; it cannot recover
    capture information clipped in the source.
    """
    image, amount = _prepare(rgb, strength)
    sigma = _sigma(radius, frame_width)
    if amount == 0:
        return image.copy()
    linear = _linear(image)
    guide = _log_luma(linear)
    mean = _blur(guide, sigma)
    variance = np.maximum(_blur(guide * guide, sigma) - mean * mean, 0)
    coefficient = variance / (variance + np.float32(.25 ** 2))
    offset = mean * (1 - coefficient)
    base = _blur(coefficient, sigma) * guide + _blur(offset, sigma)
    compression = np.float32(-math.expm1(-.36 * amount))
    raw_ev = compression * (np.float32(math.log2(.18)) - base)
    ev = 3 * np.tanh(raw_ev / 3)
    return _exposure(linear, ev)
