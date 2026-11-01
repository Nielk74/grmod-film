"""Offline display-sRGB texture experiments; no camera-equivalence claim.

These operations consume nonempty H x W x 3 float RGB in [0, 1] and return
independent float32 arrays. They approximate aesthetic ideas, not native
clarity, noise reduction, film stock, or any measured camera response.

References within this repository:
* core/src/fw/clarity.ts: eleven native Laplacian detail bands and soft-focus
  gains. Here four Gaussian difference bands reshape fine/middle luma detail,
  while coarser structure is unchanged. The kernels and gains are different.
* core/src/color/grain.ts: grain already has a midtone-weighted tone envelope
  and a scale based on a 6000-pixel-wide frame. This experiment adds ISO and
  existing-detail/noise coordination, using a different seeded noise model.

``frame_width`` is the width of the *whole rendered frame*, even for crops.
Use 6000 for native 6000px images and their 100% crops; use 2400 for a whole
frame resized to 2400px before processing. Texture and noise-synthesis sigmas
scale by frame_width / 6000; local energy estimation keeps a minimum pixel
footprint so existing output-pixel noise remains detectable. Render first
and then crop for exactly matching grain.
Re-rendering a crop with the same seed does not reproduce the full-frame
random field. Independently processed resolutions have matching nominal
scale, not a shared random field or an exact downsampling relationship.
"""

from __future__ import annotations

import math

import numpy as np
from scipy.ndimage import gaussian_filter


def _prepare(rgb: np.ndarray) -> np.ndarray:
    image = np.asarray(rgb, dtype=np.float32)
    if image.ndim != 3 or image.shape[2] != 3 or not all(image.shape[:2]):
        raise ValueError("rgb must be a nonempty H x W x 3 array")
    if not np.isfinite(image).all() or image.min() < 0 or image.max() > 1:
        raise ValueError("rgb must contain finite display-sRGB values in [0, 1]")
    return image


def _unit(value: float, name: str) -> float:
    value = float(value)
    if not math.isfinite(value) or not 0 <= value <= 1:
        raise ValueError(f"{name} must be finite and in [0, 1]")
    return value


def _scale(frame_width: float) -> float:
    width = float(frame_width)
    if not math.isfinite(width) or width <= 0:
        raise ValueError("frame_width must be finite and positive")
    return width / 6000.0


def _luma(rgb: np.ndarray) -> np.ndarray:
    # The same display-domain coefficients used by the existing grain preview.
    return rgb[..., 0] * 0.299 + rgb[..., 1] * 0.587 + rgb[..., 2] * 0.114


def _add_luma(rgb: np.ndarray, delta: np.ndarray) -> np.ndarray:
    # One shared offset preserves R-G / G-B differences even near the gamut
    # boundary; independently clipping channels would shift the colour.
    bounded = np.maximum(-rgb.min(axis=2), np.minimum(1 - rgb.max(axis=2), delta))
    return np.clip(rgb + bounded[..., None], 0, 1).astype(np.float32, copy=False)


def film_texture(
    rgb: np.ndarray,
    strength: float = 0.5,
    *,
    frame_width: float = 6000,
) -> np.ndarray:
    """Subtle fine-detail softening with modest middle-scale luma structure.

    At full strength the four band gains are 0.76, 0.92, 1.04, and 1.07,
    with Gaussian boundaries 0.65, 1.3, 2.6, and 5.2 pixels at 6000px width.
    Default strength interpolates halfway from unity. High-contrast edges
    receive less correction and the maximum luma change is 0.025*strength.
    Constants, neutral colour, and the unmodified coarser base are preserved.
    This is a Gaussian-band approximation inspired by the eleven-band native
    table, not a reproduction of its pyramid or an implementation of NR.
    """
    image = _prepare(rgb)
    amount = _unit(strength, "strength")
    scale = _scale(frame_width)
    if amount == 0:
        return image.copy()

    luma = _luma(image)
    previous = luma
    delta = np.zeros_like(luma)
    for sigma, adjustment in [(0.65, -0.24), (1.3, -0.08), (2.6, 0.04), (5.2, 0.07)]:
        blurred = gaussian_filter(luma, sigma=sigma * scale, mode="reflect")
        delta += np.float32(adjustment) * (previous - blurred)
        previous = blurred
    edge_protection = 1 / (1 + (np.abs(luma - previous) / 0.12) ** 4)
    delta *= np.float32(amount) * edge_protection
    limit = np.float32(0.025 * amount)
    delta = limit * np.tanh(delta / limit)
    return _add_luma(image, delta)


def adaptive_grain(
    rgb: np.ndarray,
    iso: float = 100,
    strength: float = 0.5,
    seed: int = 42,
    *,
    frame_width: float = 6000,
) -> np.ndarray:
    """Add reproducible achromatic grain with an ISO/detail-aware envelope.

    Default strength targets approximately 0.010 display-sRGB RMS at the
    midtone peak in a clean ISO 100 native-width patch. Two correlated noise
    scales (sigma 0.65/1.8px; 80/20 mixture) avoid uniform pixel noise.
    ISO gain is (100/max(ISO,100))**0.22. A local high-pass energy estimate
    reduces additions where noise or fine detail is already present; a
    separate broader-detail mask protects edges. This estimate cannot
    identify sensor noise independently from subject texture and performs
    no denoising. The existing project already supplies tone modulation;
    the additions here are ISO/detail coordination and multiscale noise.

    Downscaled renders also attenuate RMS by sqrt(min(frame_width/6000,1)),
    an explicit preview convention rather than exact area resampling.
    """
    image = _prepare(rgb)
    amount = _unit(strength, "strength")
    scale = _scale(frame_width)
    sensitivity = float(iso)
    if not math.isfinite(sensitivity) or sensitivity <= 0:
        raise ValueError("iso must be finite and positive")
    if amount == 0:
        return image.copy()

    luma = _luma(image)
    # Pixel-scale noise remains measurable at reduced output resolution;
    # all actual image/noise synthesis kernels retain the declared scale.
    residual = luma - gaussian_filter(luma, sigma=max(0.65 * scale, 0.65), mode="reflect")
    energy = gaussian_filter(residual * residual, sigma=max(3.0 * scale, 1.0), mode="reflect")
    existing = np.sqrt(np.maximum(energy, 0))
    detail = luma - gaussian_filter(luma, sigma=2.6 * scale, mode="reflect")

    iso_gain = (100.0 / max(sensitivity, 100.0)) ** 0.22
    target_rms = np.float32(0.020 * amount * iso_gain * math.sqrt(min(scale, 1.0)))
    existing_gate = 1 / np.sqrt(1 + (existing / (0.012 + 0.5 * target_rms)) ** 2)
    detail_gate = 1 / np.sqrt(1 + (detail / 0.055) ** 2)
    # Matches the design principle of grainTone(), with a single envelope.
    tone = np.maximum(np.sin(np.pi * np.power(luma, 0.8)), 0) ** 0.65
    tone[(luma <= 0) | (luma >= 1)] = 0

    noise = np.random.default_rng(seed).standard_normal(luma.shape, dtype=np.float32)
    grain = gaussian_filter(noise, sigma=0.65 * scale, mode="reflect")
    grain *= np.float32(0.8)
    grain += np.float32(0.2) * gaussian_filter(noise, sigma=1.8 * scale, mode="reflect")
    grain -= np.float32(grain.mean(dtype=np.float64))
    spread = float(grain.std(dtype=np.float64))
    if spread == 0:
        return image.copy()
    grain *= np.float32(1.0 / spread)
    grain *= target_rms * tone * existing_gate * detail_gate
    return _add_luma(image, grain)


def monochrome(
    rgb: np.ndarray,
    iso: float = 100,
    strength: float = 0.5,
    seed: int = 42,
    *,
    frame_width: float = 6000,
    grain_strength: float | None = None,
) -> np.ndarray:
    """Warm-filter-like mono response, gentle tone, texture, and adaptive grain.

    Strength interpolates display-luma weights from [0.299,0.587,0.114]
    toward [0.34,0.60,0.06], darkening blues relative to foliage and skin.
    The endpoint-preserving cubic tone is strictly monotonic. Fine-detail
    shaping runs at 0.6*strength and default grain at 0.8*strength. Set
    grain_strength=0 to inspect the deterministic filter/tone response.
    Strength zero with default grain is plain Rec.601 display-domain luma,
    not RGB identity. Equal R/G/B output is guaranteed; no stock is modelled.
    """
    image = _prepare(rgb)
    amount = _unit(strength, "strength")
    _scale(frame_width)
    sensitivity = float(iso)
    if not math.isfinite(sensitivity) or sensitivity <= 0:
        raise ValueError("iso must be finite and positive")
    grain_amount = 0.8 * amount if grain_strength is None else _unit(grain_strength, "grain_strength")

    weights = np.array([0.299, 0.587, 0.114], dtype=np.float32)
    weights += np.float32(amount) * np.array([0.041, 0.013, -0.054], dtype=np.float32)
    grey = image[..., 0] * weights[0] + image[..., 1] * weights[1] + image[..., 2] * weights[2]
    grey += np.float32(0.48 * amount) * grey * (1 - grey) * (2 * grey - 1)
    mono = np.repeat(np.clip(grey, 0, 1)[..., None], 3, axis=2)
    mono = film_texture(mono, strength=0.6 * amount, frame_width=frame_width)
    return adaptive_grain(mono, iso=iso, strength=grain_amount, seed=seed, frame_width=frame_width)
