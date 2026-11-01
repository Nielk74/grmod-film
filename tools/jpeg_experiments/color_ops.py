"""Independent offline colour experiments, display sRGB [0, 1] in and out.

These are interpretations for comparing real photographs, not measured film
profiles or camera-verified firmware. Arrays have any shape (..., 3), including
HxWx3 images and Nx3 colour lists. Results are new float32 arrays; inputs are
never modified. NaN/-inf become 0, +inf becomes 1, and input excursions are
clipped. Strength is finite and in [0, 1]; zero is exact sanitized identity.

Selective density is performed in OkLab: lower lightness with retained/slightly
enhanced chroma, smooth hue/chroma masks, and a broad warm-skin safeguard. Only
the explicitly graded skin_tone_colour operation tints neutral colours.

Image kernels work on 131,072 pixels at a time. A 6000x4000 float32 input/output
pair is 576 MB, with bounded scratch storage of approximately 35 MB per kernel.
Noncontiguous or non-float32 inputs may require one additional contiguous copy.
The LUT is lut[red_index, green_index, blue_index, output_channel]. It is not a
set of three one-dimensional curves: apply_lut interpolates all eight vertices.
"""

from __future__ import annotations

from collections.abc import Callable

import numpy as np


_CHUNK_PIXELS = 131_072
_M1 = np.array([[0.4122214708, 0.5363325363, 0.0514459929],
                [0.2119034982, 0.6806995451, 0.1073969566],
                [0.0883024619, 0.2817188376, 0.6299787005]], dtype=np.float32)
_M2 = np.array([[0.2104542553, 0.7936177850, -0.0040720468],
                [1.9779984951, -2.4285922050, 0.4505937099],
                [0.0259040371, 0.7827717662, -0.8086757660]], dtype=np.float32)
_IM1 = np.array([[4.0767416621, -3.3077115913, 0.2309699292],
                 [-1.2684380046, 2.6097574011, -0.3413193965],
                 [-0.0041960863, -0.7034186147, 1.7076147010]], dtype=np.float32)
_IM2 = np.array([[1, 0.3963377774, 0.2158037573],
                 [1, -0.1055613458, -0.0638541728],
                 [1, -0.0894841775, -1.2914855480]], dtype=np.float32)


def _strength(value: float) -> float:
    value = float(value)
    if not np.isfinite(value) or not 0 <= value <= 1:
        raise ValueError("strength must be finite and between 0 and 1")
    return value


def _input(rgb: np.ndarray) -> np.ndarray:
    arr = np.asarray(rgb, dtype=np.float32)
    if arr.ndim < 2 or arr.shape[-1] != 3:
        raise ValueError("rgb must have shape (..., 3), e.g. HxWx3 or Nx3")
    return arr


def _clean(chunk: np.ndarray) -> np.ndarray:
    result = np.nan_to_num(chunk, copy=True, nan=0.0, posinf=1.0, neginf=0.0)
    np.clip(result, 0, 1, out=result)
    return result


def _process(rgb: np.ndarray, strength: float,
             kernel: Callable[[np.ndarray, float], np.ndarray]) -> np.ndarray:
    value = _strength(strength)
    arr = _input(rgb)
    flat = arr.reshape(-1, 3)
    output = np.empty(arr.shape, dtype=np.float32)
    output_flat = output.reshape(-1, 3)
    for start in range(0, len(flat), _CHUNK_PIXELS):
        end = min(start + _CHUNK_PIXELS, len(flat))
        chunk = _clean(flat[start:end])
        # Below float32 precision, a colour-space round trip adds more error
        # than the requested effect. This also avoids a tiny shoulder divisor.
        result = chunk if value <= np.finfo(np.float32).eps else kernel(chunk, value)
        np.clip(result, 0, 1, out=result)
        output_flat[start:end] = result
    return output


def _smooth(low: float, high: float, x: np.ndarray) -> np.ndarray:
    t = np.clip((x - low) / (high - low), 0, 1)
    return t * t * (3 - 2 * t)


def _to_linear(rgb: np.ndarray) -> np.ndarray:
    return np.where(rgb <= 0.04045, rgb / 12.92,
                    ((rgb + 0.055) / 1.055) ** 2.4).astype(np.float32, copy=False)


def _to_display(linear: np.ndarray) -> np.ndarray:
    positive = np.maximum(linear, 0)
    return np.where(positive <= 0.0031308, positive * 12.92,
                    1.055 * positive ** (1 / 2.4) - 0.055).astype(np.float32, copy=False)


def _to_lab(rgb: np.ndarray) -> np.ndarray:
    lms = _to_linear(rgb) @ _M1.T
    np.cbrt(lms, out=lms)
    return lms @ _M2.T


def _lab_to_linear(lab: np.ndarray) -> np.ndarray:
    lms = lab @ _IM2.T
    np.power(lms, 3, out=lms)
    return lms @ _IM1.T


def _gamut_linear(lab: np.ndarray, knee: float) -> np.ndarray:
    """Smoothly contract linear-RGB chroma about the OkLab neutral anchor.

    The ray's exact intersection with the RGB cube is analytic, so there is no
    branch ambiguity at the non-convex saturated-blue cusp of OkLab. Compression
    keeps the linear RGB chroma direction. OkLab hue is unchanged where no
    compression is needed, and can shift slightly at extreme gamut boundaries.
    The soft knee is C1 continuous and approaches the boundary asymptotically.
    """
    linear = _lab_to_linear(lab)
    anchor = np.clip(lab[:, 0] ** 3, 0, 1)[:, None]
    delta = linear - anchor
    positive = np.maximum(delta, 0) / np.maximum(1 - anchor, 1e-7)
    negative = np.maximum(-delta, 0) / np.maximum(anchor, 1e-7)
    radius = np.maximum(positive, negative).max(axis=1)
    excess = np.maximum(radius - knee, 0)
    soft_radius = knee - (1 - knee) * np.expm1(-excess / (1 - knee))
    compressed = np.where(radius > knee, soft_radius, radius)
    scale = np.minimum(compressed / np.maximum(radius, 1e-7), 1)
    return anchor + delta * scale[:, None]


def _from_lab(lab: np.ndarray, strength: float) -> np.ndarray:
    # Only the outermost 1.5% of the RGB gamut ray receives the full-strength knee.
    # highlight_gamut deliberately uses an earlier and stronger compression.
    return _to_display(_gamut_linear(lab, 1 - 0.015 * strength))


def _polar(lab: np.ndarray) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    return (lab[:, 0], np.hypot(lab[:, 1], lab[:, 2]),
            np.rad2deg(np.arctan2(lab[:, 2], lab[:, 1])))


def _hue(hue: np.ndarray, centre: float, width: float) -> np.ndarray:
    distance = np.abs((hue - centre + 180) % 360 - 180)
    return 0.5 + 0.5 * np.cos(np.pi * np.minimum(distance / width, 1))


def _skin(lightness: np.ndarray, chroma: np.ndarray, hue: np.ndarray) -> np.ndarray:
    """Broad warm-colour safeguard, not face/skin segmentation.

    Includes low/moderate-chroma skin over a wide exposure range; high-chroma
    oranges are released gradually. Warm objects can also receive protection.
    """
    return (_hue(hue, 52, 62) * _smooth(0.006, 0.025, chroma)
            * (1 - _smooth(0.15, 0.24, chroma)) * _smooth(0.10, 0.30, lightness))


def _preserve_neutral(source: np.ndarray, result: np.ndarray) -> np.ndarray:
    neutral = np.ptp(source, axis=1) <= 1e-7
    result[neutral] = source[neutral]
    return result


def _density_kernel(rgb: np.ndarray, strength: float) -> np.ndarray:
    lab = _to_lab(rgb)
    lightness, chroma, hue = _polar(lab)
    weight = (_smooth(0.025, 0.18, chroma) * _smooth(0.08, 0.30, lightness)
              * (1 - 0.65 * _smooth(0.80, 0.99, lightness))
              * (1 - 0.84 * _skin(lightness, chroma, hue)))
    lab[:, 0] -= 0.045 * strength * weight
    lab[:, 1:] *= (1 + 0.065 * strength * weight)[:, None]
    return _preserve_neutral(rgb, _from_lab(lab, strength))


def colour_density(rgb: np.ndarray, strength: float = 0.6) -> np.ndarray:
    """Enrich chromatic midtones with restrained density and warm-skin protection.

    At full strength, maximum OkLab lightness reduction is 0.045 and maximum
    chroma gain 6.5%. Low-chroma surfaces and achromatic tones are spared.
    """
    return _process(rgb, strength, _density_kernel)


def _blue_kernel(rgb: np.ndarray, strength: float) -> np.ndarray:
    lab = _to_lab(rgb)
    lightness, chroma, hue = _polar(lab)
    weight = (_hue(hue, 250, 72) * _smooth(0.022, 0.105, chroma)
              * _smooth(0.10, 0.30, lightness)
              * (1 - 0.70 * _smooth(0.80, 0.98, lightness)))
    lab[:, 0] -= 0.065 * strength * weight
    return _preserve_neutral(rgb, _from_lab(lab, strength))


def blue_density(rgb: np.ndarray, strength: float = 0.5) -> np.ndarray:
    """Deepen blue/cyan colour independently of hue, without a teal channel mix.

    A cosine band centred at OkLab hue 250 degrees, with a 72-degree half-width,
    changes L by at most 0.065 at full strength. Chroma is held until gamut
    protection is necessary, where a smooth linear-RGB chroma contraction
    prevents clipping; extreme gamut colours may then shift slightly in hue.
    """
    return _process(rgb, strength, _blue_kernel)


def _highlight_kernel(rgb: np.ndarray, strength: float) -> np.ndarray:
    lab = _to_lab(rgb)
    lightness = lab[:, 0]
    knee = 0.70
    above = np.maximum(lightness - knee, 0)
    alpha = 0.42 * strength
    # expm1 retains precision around the C1-continuous shoulder knee.
    mapped = knee - (1 - knee) * np.expm1(-alpha * above / (1 - knee)) / alpha
    lab[:, 0] = np.where(lightness > knee, mapped, lightness)
    anchor = np.clip(lab[:, 0] ** 3, 0, 1)[:, None]
    gamut_knee = 1 - 0.24 * strength + 0.12 * strength * strength
    result = _to_display(_gamut_linear(lab, gamut_knee))
    neutral = np.ptp(rgb, axis=1) <= 1e-7
    if np.any(neutral):
        # Avoid insignificant colour-space roundoff tint on an achromatic ramp.
        grey = _to_display(anchor[neutral])
        result[neutral] = grey
    return result


def highlight_gamut(rgb: np.ndarray, strength: float = 0.5) -> np.ndarray:
    """Monotone highlight shoulder plus smooth radial gamut compression.

    The OkLab L shoulder starts at 0.70 with unit slope and remains strictly
    increasing. Gamut compression starts near 91% of the linear RGB gamut ray
    at default strength, approaching the boundary smoothly without a hard clip.
    This reshapes available JPEG highlights; it cannot recover capture clipping.
    """
    return _process(rgb, strength, _highlight_kernel)


def _skin_colour_kernel(rgb: np.ndarray, strength: float) -> np.ndarray:
    lab = _to_lab(rgb)
    lightness, chroma, hue = _polar(lab)
    skin = _skin(lightness, chroma, hue)
    shadow = (1 - _smooth(0.25, 0.63, lightness)) * _smooth(0.0, 0.12, lightness)
    high = _smooth(0.65, 0.94, lightness) * (1 - _smooth(0.94, 1, lightness))
    middle = _smooth(0.25, 0.55, lightness) * (1 - _smooth(0.74, 0.96, lightness))
    freedom = 1 - 0.90 * skin
    saturation = 1 + strength * freedom * (0.09 * middle - 0.08 * shadow - 0.14 * high)
    angle = np.deg2rad(strength * freedom * middle
                      * (3.5 * _hue(hue, 145, 55) - 1.5 * _hue(hue, 250, 60)))
    a, b = lab[:, 1].copy(), lab[:, 2].copy()
    cosine, sine = np.cos(angle), np.sin(angle)
    lab[:, 1] = saturation * (a * cosine - b * sine)
    lab[:, 2] = saturation * (a * sine + b * cosine)
    # Deliberate graded tint: cool shadows, warm highlights. At endpoints it is 0.
    tint = strength * freedom
    lab[:, 1] += tint * (-0.0025 * shadow + 0.0020 * high)
    lab[:, 2] += tint * (-0.0050 * shadow + 0.0050 * high)
    result = _from_lab(lab, strength)
    endpoint = np.all(rgb == 0, axis=1) | np.all(rgb == 1, axis=1)
    result[endpoint] = rgb[endpoint]
    return result


def skin_tone_colour(rgb: np.ndarray, strength: float = 0.5) -> np.ndarray:
    """Brightness-dependent colour with a broad low/moderate-chroma skin safeguard.

    Mid-colour gains up to 9% chroma, shadows lose up to 8%, highlights up to
    14%, with gentle green/blue hue shaping. Warm skin gets up to 90% protection.
    Unlike the selective density tools, neutral shadows deliberately receive a
    small cool tint and highlights a warm tint. Black and white stay anchored.
    """
    return _process(rgb, strength, _skin_colour_kernel)


def _target_kernel(rgb: np.ndarray, unused_strength: float) -> np.ndarray:
    result = _density_kernel(rgb, 0.45)
    result = _blue_kernel(result, 0.35)
    result = _skin_colour_kernel(result, 0.45)
    return _highlight_kernel(result, 0.35)


def lut_target(rgb: np.ndarray) -> np.ndarray:
    """Direct target sampled by build_lut, in the same display-sRGB float domain.

    In order: density .45, independent blue density .35, skin/tone colour .45,
    highlight/gamut .35. The hue/chroma/brightness interaction is nonseparable;
    it cannot be represented exactly by three independent channel curves.
    This is an original comparison recipe, not a named-camera simulation.
    """
    return _process(rgb, 1.0, _target_kernel)


def build_lut(size: int = 17) -> np.ndarray:
    """Sample lut_target on a uniform size-cube, ordered lut[r,g,b,channel]."""
    if isinstance(size, bool) or not isinstance(size, (int, np.integer)) or not 2 <= size <= 129:
        raise ValueError("LUT size must be an integer between 2 and 129")
    axis = np.linspace(0, 1, size, dtype=np.float32)
    grid = np.stack(np.meshgrid(axis, axis, axis, indexing="ij"), axis=-1)
    return lut_target(grid)


def apply_lut(rgb: np.ndarray, lut: np.ndarray) -> np.ndarray:
    """Apply actual 3D trilinear interpolation, with red/green/blue index order.

    The cube has shape (N,N,N,3), with 2 <= N. Each pixel is a weighted sum
    of all eight corners of its enclosing cell. Endpoints map exactly to cube
    corners; invalid RGB is sanitized as for the other functions. LUT values
    must be finite in [0,1]. The input image and cube remain unmodified.
    """
    arr = _input(rgb)
    cube = np.asarray(lut, dtype=np.float32)
    if (cube.ndim != 4 or cube.shape[-1] != 3 or cube.shape[0] < 2
            or cube.shape[0] != cube.shape[1] or cube.shape[1] != cube.shape[2]):
        raise ValueError("lut must have shape (N, N, N, 3), N >= 2")
    if not np.isfinite(cube).all() or np.any((cube < 0) | (cube > 1)):
        raise ValueError("lut values must be finite and within [0, 1]")
    size = cube.shape[0]
    flat = arr.reshape(-1, 3)
    output = np.empty(arr.shape, dtype=np.float32)
    out = output.reshape(-1, 3)
    for start in range(0, len(flat), _CHUNK_PIXELS):
        end = min(start + _CHUNK_PIXELS, len(flat))
        position = _clean(flat[start:end]) * (size - 1)
        low = np.minimum(position.astype(np.intp), size - 2)
        weight = position - low
        r, g, b = low.T
        wr, wg, wb = weight.T.astype(np.float32, copy=False)
        result = np.zeros((end - start, 3), dtype=np.float32)
        for ri in (0, 1):
            for gi in (0, 1):
                for bi in (0, 1):
                    w = ((wr if ri else 1 - wr) * (wg if gi else 1 - wg)
                         * (wb if bi else 1 - wb))
                    result += cube[r + ri, g + gi, b + bi] * w[:, None]
        np.clip(result, 0, 1, out=result)
        out[start:end] = result
    return output
